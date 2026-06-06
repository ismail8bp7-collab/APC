import sqlite3
import time
from datetime import datetime

from asyncua.sync import Client


# =====================================================
# CONFIG
# =====================================================

ENDPOINT = "opc.tcp://DESKTOP-8KTMG4V:4870"
DB_FILE = "plc_data.db"

NODES = {
    "R1_PH": 'ns=3;s=R1-PH',
    "R1_TCCY": 'ns=3;s=R1-TCCY',
    "R1_TOX": 'ns=3;s=R1-TOX',
    "R2_TCCY": 'ns=3;s=R2-TCCY',
    "R6_TCCY": 'ns=3;s=R6-TCCY',
    "R7_PH": 'ns=3;s=R7-PH',
    "R7_TOX": 'ns=3;s=R7-TOX',
}


# =====================================================
# DATABASE
# =====================================================

def create_table(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS plc_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            R1_PH REAL,
            R1_TCCY REAL,
            R1_TOX REAL,
            R2_TCCY REAL,
            R6_TCCY REAL,
            R7_PH REAL,
            R7_TOX REAL
        )
    """)

    conn.commit()


def insert_reading(conn: sqlite3.Connection, row: dict) -> None:
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO plc_readings (
            timestamp,
            R1_PH,
            R1_TCCY,
            R1_TOX,
            R2_TCCY,
            R6_TCCY,
            R7_PH,
            R7_TOX
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        row["timestamp"],
        row["R1_PH"],
        row["R1_TCCY"],
        row["R1_TOX"],
        row["R2_TCCY"],
        row["R6_TCCY"],
        row["R7_PH"],
        row["R7_TOX"],
    ))

    conn.commit()


# =====================================================
# VALIDATION
# =====================================================

def is_valid_row(row: dict) -> bool:
    """
    Vérifie que toutes les valeurs PLC sont valides.
    Si une valeur est None, on considère que OPC UA est déconnecté
    ou que la lecture est invalide.
    """

    plc_values = {
        key: value
        for key, value in row.items()
        if key != "timestamp"
    }

    # Si une valeur est None => ligne invalide
    if any(value is None for value in plc_values.values()):
        return False

    # Si toutes les valeurs sont None => ligne invalide
    if all(value is None for value in plc_values.values()):
        return False

    return True


# =====================================================
# OPC UA
# =====================================================

def read_once(client: Client) -> dict:
    row = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    for tag_name, node_id in NODES.items():
        try:
            node = client.get_node(node_id)
            value = node.read_value()

            # Sécurité : convertir en float si possible
            if value is not None:
                value = float(value)

            row[tag_name] = value

        except Exception as e:
            print(f"⚠️ Erreur lecture {tag_name}: {e}")
            row[tag_name] = None

    return row


# =====================================================
# MAIN
# =====================================================

def main():
    conn = sqlite3.connect(DB_FILE)
    create_table(conn)

    print(f"✅ Base créée/ouverte : {DB_FILE}")

    while True:
        try:
            print("\n🔄 Tentative de connexion OPC UA...")
            
            with Client(ENDPOINT) as client:
                print("✅ Connecté au serveur OPC UA")

                while True:
                    row = read_once(client)

                    print("\n==============================")
                    print("TIME:", row["timestamp"])
                    print("==============================")

                    for key, value in row.items():
                        if key != "timestamp":
                            print(f"{key:10s} = {value}")

                    if is_valid_row(row):
                        insert_reading(conn, row)
                        print("Ligne insérée dans la base")
                        time.sleep(1)

                    else:
                        print(" OPC UA déconnecté / valeurs invalides")
                        print(" Ligne NON insérée dans la base")
                        print(" Fermeture de la session OPC UA actuelle...")
                        print(" Nouvelle tentative dans 3 secondes...")

                        # Important : sortir de la boucle interne
                        # Le bloc with se ferme, puis la boucle externe relance une connexion
                        break

        except Exception as e:
            print("\n❌ Connexion OPC UA perdue ou impossible :", e)
            print("⏳ Nouvelle tentative dans 3 secondes...")

        time.sleep(3)


if __name__ == "__main__":
    main()