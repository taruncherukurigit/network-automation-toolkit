"""
Compatibility patch for legacy Cisco IOS SSH servers (e.g. the 1921, 3560E)
that incorrectly respond to a signed publickey auth request with a
PK_OK-style "please send the signature" message, even though the
signature was already included. Modern Paramiko doesn't expect this
reply during publickey auth and raises "Illegal info request from
server". This patch caches the last signed publickey message sent and,
if the server asks again, simply resends it verbatim -- satisfying the
device's (redundant) request instead of erroring out.

Root cause: legacy Cisco IOS SSH servers don't strictly follow
RFC 4252's publickey auth flow. Paramiko sends the signed proof
immediately (a valid protocol shortcut); these IOS versions incorrectly
respond as if only the unsigned "would you accept this key" probe had
been sent, asking for the signature a second time.

Background reading:
  https://github.com/paramiko/paramiko/issues/122
  https://github.com/ktbyers/netmiko/issues/904

See docs/TROUBLESHOOTING-LOG.md for the full diagnostic story.
"""
import paramiko.transport
import paramiko.auth_handler
from paramiko.auth_handler import AuthHandler

_original_send_message = paramiko.transport.Transport._send_message
_original_info_request = AuthHandler._parse_userauth_info_request


def _patched_send_message(self, data):
    # Remember the last message sent while doing publickey auth,
    # in case the device asks for it again.
    if getattr(self, "auth_handler", None) and \
            getattr(self.auth_handler, "auth_method", None) == "publickey":
        self._last_pubkey_auth_message = data
    return _original_send_message(self, data)


def _patched_info_request(self, m):
    if self.auth_method == "publickey":
        last_msg = getattr(self.transport, "_last_pubkey_auth_message", None)
        if last_msg is not None:
            # Legacy IOS quirk: resend the same signed request instead of erroring.
            self.transport._send_message(last_msg)
            return
    return _original_info_request(self, m)


paramiko.transport.Transport._send_message = _patched_send_message
AuthHandler._parse_userauth_info_request = _patched_info_request
