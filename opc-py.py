from asyncua.sync import Client

endpoint = "opc.tcp://192.168.11.105:4870"

with Client(endpoint) as client:
    print("Connecté au serveur OPC UA")

    root = client.get_root_node()
    print("\nROOT:", root)

    objects = client.get_objects_node()
    print("OBJECTS:", objects)

    print("\n=== CHILDREN OF OBJECTS ===")
    children = objects.get_children()

    for i, child in enumerate(children, start=1):
        try:
            browse_name = child.read_browse_name()
            display_name = child.read_display_name()
            node_id = child.nodeid

            print(f"\n[{i}]")
            print("BrowseName :", browse_name)
            print("DisplayName:", display_name)
            print("NodeId     :", node_id)

        except Exception as e:
            print(f"Erreur sur child {i}: {e}")