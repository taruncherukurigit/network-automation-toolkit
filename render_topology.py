import json
import re
import graphviz

with open("topology.json") as f:
    edges = json.load(f)

def clean_label(name):
    return re.split(r"\.(yourdomain|cherwood)", name)[0].upper()

BG = "#0a0e14"
NODE_FILL = "#0f151d"
GRID_LINE = "#2a323d"
CYAN = "#3ddad7"
AMBER = "#f5a623"
TEXT = "#c9d1d9"

dot = graphviz.Graph(comment="Cherwood Network Topology", format="svg")
dot.attr(
    rankdir="LR",
    bgcolor=BG,
    fontname="Liberation Mono",
    fontcolor=TEXT,
    label="CHERWOOD NETWORK SOLUTIONS // LIVE TOPOLOGY",
    labelloc="t",
    fontsize="16",
    pad="0.4",
    nodesep="0.6",
    ranksep="0.8",
)
dot.attr("node", fontname="Liberation Mono", fontsize="12", style="filled",
          fillcolor=NODE_FILL, fontcolor=CYAN, penwidth="1.4", margin="0.25,0.15")
dot.attr("edge", fontname="Liberation Mono", fontsize="9", fontcolor=GRID_LINE,
          color=GRID_LINE, penwidth="1.1")

STYLES = {
    "FortiGate": {"shape": "diamond", "color": AMBER, "fontcolor": AMBER},
    "3560E": {"shape": "box", "color": CYAN},
    "1921": {"shape": "box", "color": CYAN},
}
DEFAULT_STYLE = {"shape": "hexagon", "color": CYAN}

added_nodes = set()

def add_node(name):
    if name in added_nodes:
        return
    style = STYLES.get(name, DEFAULT_STYLE)
    dot.node(name, label=clean_label(name), **style)
    added_nodes.add(name)

for e in edges:
    add_node(e["device_a"])
    add_node(e["device_b"])
    edge_label = f'{e["port_a"]} <-> {e["port_b"]}'.upper()
    dot.edge(e["device_a"], e["device_b"], label=edge_label)

output_path = dot.render("topology", cleanup=True)
print(f"Rendered to {output_path}")