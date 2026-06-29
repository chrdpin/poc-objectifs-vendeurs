import streamlit as st
import pandas as pd
from snowflake.snowpark import Session






import streamlit as st
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

st.warning("⚠️ GÉNÉRATEUR DE CLÉS SÉCURISÉ ⚠️")
mot_de_passe = st.text_input("Entrez le code PIN pour générer les clés :", type="password")

if mot_de_passe == "POC2026!": # Seul toi connais ce code
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_key = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    public_key = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    st.text("CLÉ PRIVÉE (Pour les Secrets Streamlit) :")
    st.code(private_key.decode('utf-8'))
    st.text("CLÉ PUBLIQUE (Pour Snowflake) :")
    st.code(public_key.decode('utf-8'))

st.stop()














# 1. Configuration graphique
st.set_page_config(page_title="🎯 Saisie des Objectifs VN", layout="wide")
st.title("🎯 Pilotage des Objectifs VN par Vendeur")

connection_parameters = st.secrets["snowflake"]
session = Session.builder.configs(connection_parameters).create()

# --- SIMULATION DE CONNEXION MANAGERIALE (LHM) ---
gerant_connecte = st.sidebar.selectbox("Simuler connexion en tant que :", ["Gérant 1", "Gérant 2"])
id_gerant = "G-001" if gerant_connecte == "Gérant 1" else "G-002"
st.sidebar.write(f"Droits d'accès : **{gerant_connecte}**")

# --- CHARGEMENT DES FILTRES ---
query_vendeurs = f"SELECT ID_VENDEUR, NOM_PRENOM_VENDEUR FROM T_VENDEURS_LHM WHERE ID_GERANT = '{id_gerant}'"
df_vendeurs = session.sql(query_vendeurs).to_pandas()

if not df_vendeurs.empty:
    
    # Disposition des deux listes déroulantes côte à côte
    col_vendeur, col_annee = st.columns(2)
    
    with col_vendeur:
        vendeur_choisi = st.selectbox("1. Choisir le Vendeur :", options=df_vendeurs['NOM_PRENOM_VENDEUR'].tolist())
        id_vendeur = df_vendeurs[df_vendeurs['NOM_PRENOM_VENDEUR'] == vendeur_choisi]['ID_VENDEUR'].values[0]
        
    with col_annee:
        annee_choisie = st.selectbox("2. Choisir l'Année :", options=[2026, 2027, 2025], index=0)

    st.write("---")
    st.subheader(f"Grille des objectifs VN pour {vendeur_choisi} ({annee_choisie})")

    # --- ARCHITECTURE DE LA GRILLE DES 12 MOIS ---
    structure_mois = [
        {"Mois_Num": "01", "Mois": "Janvier"}, {"Mois_Num": "02", "Mois": "Février"},
        {"Mois_Num": "03", "Mois": "Mars"}, {"Mois_Num": "04", "Mois": "Avril"},
        {"Mois_Num": "05", "Mois": "Mai"}, {"Mois_Num": "06", "Mois": "Juin"},
        {"Mois_Num": "07", "Mois": "Juillet"}, {"Mois_Num": "08", "Mois": "Août"},
        {"Mois_Num": "09", "Mois": "Septembre"}, {"Mois_Num": "10", "Mois": "Octobre"},
        {"Mois_Num": "11", "Mois": "Novembre"}, {"Mois_Num": "12", "Mois": "Décembre"}
    ]
    df_template = pd.DataFrame(structure_mois)
    df_template["ANNEE_MOIS"] = df_template["Mois_Num"].apply(lambda x: f"{annee_choisie}-{x}")

    # Récupération des données existantes (on a ajouté NOM_VENDEUR mais on ne l'affiche pas dans la grille éditable)
    query_existante = f"""
        SELECT ANNEE_MOIS, VOLUME_OBJECTIF_VN 
        FROM T_OBJECTIFS_STREAMLIT 
        WHERE ID_VENDEUR = '{id_vendeur}' AND ANNEE_MOIS LIKE '{annee_choisie}-%'
    """
    df_base_donnees = session.sql(query_existante).to_pandas()

    if not df_base_donnees.empty:
        df_final = pd.merge(df_template, df_base_donnees, on="ANNEE_MOIS", how="left")
        df_final["VOLUME_OBJECTIF_VN"] = df_final["VOLUME_OBJECTIF_VN"].fillna(0).astype(int)
    else:
        df_final = df_template.copy()
        df_final["VOLUME_OBJECTIF_VN"] = 0

    # On n'affiche que le mois et le volume pour que le gérant reste focus
    df_editeur = df_final[["Mois", "VOLUME_OBJECTIF_VN"]].copy()

    grille_editee = st.data_editor(
        df_editeur,
        disabled=["Mois"], 
        use_container_width=True,
        key="grille_vn"
    )

    # --- SÉCURISATION DE L'ENREGISTREMENT (MERGE AVEC LE NOM) ---
    if st.button("💾 Enregistrer la grille d'objectifs"):
        
        df_sauvegarde = grille_editee.copy()
        df_sauvegarde["ANNEE_MOIS"] = df_template["ANNEE_MOIS"]
        df_sauvegarde["ID_VENDEUR"] = id_vendeur
        
        # MODIFICATION ICI : On injecte le nom textuel du vendeur choisi dans le tableau d'envoi
        df_sauvegarde["NOM_VENDEUR"] = vendeur_choisi

        # On inclut bien la colonne NOM_VENDEUR pour la table temporaire
        df_envoi = df_sauvegarde[["ID_VENDEUR", "NOM_VENDEUR", "ANNEE_MOIS", "VOLUME_OBJECTIF_VN"]].copy()

        # ASTUCE : On renomme la table temporaire en V2 pour forcer Snowflake à la recréer proprement
        # On convertit le dataframe pandas en dataframe natif Snowpark, puis on l'écrit proprement
        df_snowpark = session.create_dataframe(df_envoi)
        df_snowpark.write.mode("overwrite").save_as_table("TEMP_OBJ_VN_V2", table_type="temporary")
        

        # Mise à jour du MERGE avec la table V2
        merge_sql = f"""
            MERGE INTO T_OBJECTIFS_STREAMLIT target
            USING TEMP_OBJ_VN_V2 source
            ON target.ID_VENDEUR = source.ID_VENDEUR AND target.ANNEE_MOIS = source.ANNEE_MOIS
            WHEN MATCHED THEN
                UPDATE SET 
                    target.NOM_VENDEUR = source.NOM_VENDEUR,
                    target.VOLUME_OBJECTIF_VN = source.VOLUME_OBJECTIF_VN,
                    target.DATE_MODIFICATION = CURRENT_TIMESTAMP(),
                    target.MODIFIE_PAR_UTILISATEUR = '{gerant_connecte}'
            WHEN NOT MATCHED THEN
                INSERT (ID_VENDEUR, NOM_VENDEUR, ANNEE_MOIS, VOLUME_OBJECTIF_VN, DATE_MODIFICATION, MODIFIE_PAR_UTILISATEUR)
                VALUES (source.ID_VENDEUR, source.NOM_VENDEUR, source.ANNEE_MOIS, source.VOLUME_OBJECTIF_VN, CURRENT_TIMESTAMP(), '{gerant_connecte}');
        """
        session.sql(merge_sql).collect()
        
        st.success(f"✅ Objectifs VN de {vendeur_choisi} sauvegardés avec le nom en base !")
        st.rerun()

else:
    st.warning("Aucun vendeur trouvé pour ce profil de gérant.")
