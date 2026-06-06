from asyncua.sync import Client
from datetime import datetime
import time

endpoint = "opc.tcp://192.168.11.105:4870"

nodes = {
    "R1_PH": 'ns=3;s=R1-PH',
    "R1_TCCY": 'ns=3;s=R1-TCCY',
    "R1_TOX": 'ns=3;s=R1-TOX',
    "R2_TCCY": 'ns=3;s=R2-TCCY',
    "R6_TCCY": 'ns=3;s=R6-TCCY',
    "R7_PH": 'ns=3;s=R7-PH',
    "R7_TOX": 'ns=3;s=R7-TOX',
}

print("Début du script...")

with Client(endpoint) as client:
    print("✅ Connecté au serveur OPC UA")

    opc_nodes = {name: client.get_node(node_id) for name, node_id in nodes.items()}

    while True:
        print("\n==============================")
        print("TIME:", datetime.now())
        print("==============================")

        for name, node in opc_nodes.items():
            try:
                value = node.read_value()
                print(f"{name:10s} = {value}")
            except Exception as e:
                print(f"{name:10s} = ERROR ({e})")

        time.sleep(1)