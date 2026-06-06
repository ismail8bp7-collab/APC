from asyncua.sync import Client

endpoint = "opc.tcp://192.168.11.105:4870"
prediction_node_id = "ns=3;s=REJET_PREDIT"   # à adapter avec le vrai NodeId
prediction_value = 0.4742712403329723

with Client(endpoint) as client:
    node = client.get_node(prediction_node_id)
    node.write_value(float(prediction_value))

print("✅ Prédiction écrite dans le PLC :", prediction_value)