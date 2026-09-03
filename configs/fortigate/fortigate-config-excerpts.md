# FortiGate — Configuration Excerpts (Sanitized)

The FortiGate's full configuration export runs ~36,000 lines, most of it default FortiSwitch/wireless-controller boilerplate not applicable to this hardware (same approach used in the [Cherwood Health FortiGate excerpts](https://github.com/taruncherukurigit/cherwood-health/blob/main/configs/fortigate/fortigate-config-excerpts.md)). Below are the sections directly relevant to this project — the VLAN 60 interface and the four firewall policies built for Cherwood Network Solutions.

## VLAN 60 interface

```
edit "VLAN60_NetSoln"
    set vdom "root"
    set vrf 0
    set mode static
    set dhcp-relay-interface-select-method auto
    set dhcp-relay-service disable
    set ip 10.10.60.1 255.255.255.0
    set allowaccess ping https ssh
    set fail-detect disable
    set pptp-client disable
    set arpforward enable
    set broadcast-forward disable
    set bfd global
    set l2forward disable
    set icmp-send-redirect enable
    set icmp-accept-redirect enable
```

## Firewall policies

Four policies, all originating from VLAN60_NetSoln — narrow, explicit, with a logged DENY backstop. Full design rationale in [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md).

### NetSoln_to_Switch_MGMT

```
set status enable
set name "NetSoln_to_Switch_MGMT"
set srcintf "VLAN60_NetSoln"
set dstintf "VLAN10_Trusted"
set action accept
set srcaddr "all"
set dstaddr "Switch_MGMT"
set schedule "always"
set service "SNMP" "SSH"
```

### NetSoln_to_Branch_MGMT

```
set status enable
set name "NetSoln_to_Branch_MGMT"
set srcintf "VLAN60_NetSoln"
set dstintf "internal2"
set action accept
set srcaddr "all"
set dstaddr "Router1921_MGMT"
set schedule "always"
set service "SNMP" "SSH"
```

### NetSoln_to_Internet

```
set status enable
set name "NetSoln_to_Internet"
set srcintf "VLAN60_NetSoln"
set dstintf "wan1"
set action accept
set srcaddr "all"
set dstaddr "all"
set schedule "always"
set service "ALL"
```

### NetSoln_to_Core_DENY

```
set status enable
set name "NetSoln_to_Core_DENY"
set srcintf "VLAN60_NetSoln"
set dstintf "VLAN10_Trusted"
set action deny
set srcaddr "all"
set dstaddr "all"
set schedule "always"
set service "ALL"
set logtraffic all
```

Policy ordering places `NetSoln_to_Core_DENY` directly below `NetSoln_to_Switch_MGMT` in the same interface-pair group, so the narrow ACCEPT rule matches first — confirmed via the live FortiGate policy list during the build.
