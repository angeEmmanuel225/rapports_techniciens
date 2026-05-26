#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
============================================================
  SERVEUR RENDER — Gestionnaire de Rapports Techniciens
  Déployer sur Render.com comme Web Service Python
  ─────────────────────────────────────────────────────
  requirements.txt :
      flask
      gunicorn

  Commande de démarrage Render :
      gunicorn server_render:app

  Variables d'environnement Render :
      PORT  (fournie automatiquement par Render)
============================================================
"""

import os
import json
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

DB_FILE = 'rapports_render.db'

# ──────────────────────────────────────────────────────────
#  BASE DE DONNÉES
# ──────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    # Table principale des rapports journaliers
    c.execute('''
        CREATE TABLE IF NOT EXISTS rapports (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            nom                  TEXT    NOT NULL DEFAULT '',
            prenom               TEXT    NOT NULL DEFAULT '',
            responsable          TEXT    DEFAULT '',
            departement          TEXT    DEFAULT '',
            heure_debut_journee  TEXT    DEFAULT '',
            heure_fin_journee    TEXT    DEFAULT '',
            date                 TEXT    DEFAULT '',
            timestamp            TEXT    DEFAULT '',
            taches               TEXT    DEFAULT '[]',
            commandes            TEXT    DEFAULT '[]',
            signature            TEXT    DEFAULT '[]'
        )
    ''')

    # Table des commandes de pièces autonomes (depuis l'écran dédié)
    c.execute('''
        CREATE TABLE IF NOT EXISTS commandes_standalone (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            technicien    TEXT    DEFAULT '',
            departement   TEXT    DEFAULT '',
            nom_piece     TEXT    DEFAULT '',
            reference     TEXT    DEFAULT '',
            quantite      TEXT    DEFAULT '',
            urgence       TEXT    DEFAULT 'Normal',
            machine       TEXT    DEFAULT '',
            justification TEXT    DEFAULT '',
            date          TEXT    DEFAULT '',
            timestamp     TEXT    DEFAULT '',
            statut        TEXT    DEFAULT 'En attente'
        )
    ''')

    conn.commit()
    conn.close()


init_db()


# ──────────────────────────────────────────────────────────
#  ROUTES
# ──────────────────────────────────────────────────────────

@app.route('/', methods=['GET'])
def index():
    """Page d'accueil – santé du serveur."""
    return jsonify({
        'status': 'ok',
        'service': 'Gestionnaire de Rapports Techniciens',
        'version': '2.0',
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })


@app.route('/ping', methods=['GET'])
def ping():
    """Vérification de disponibilité."""
    return jsonify({'status': 'ok', 'message': 'Serveur Render actif ✅'})


# ── Réception d'un rapport complet depuis le mobile ───────

@app.route('/api/rapport', methods=['POST'])
def receive_rapport():
    """
    Reçoit un rapport journalier depuis l'application mobile.

    Corps JSON attendu :
    {
        "nom": "Dupont",
        "prenom": "Jean",
        "responsable": "M. Martin",
        "departement": "Maintenance",
        "heure_debut_journee": "07:30",
        "heure_fin_journee": "16:00",
        "date": "26/05/2025",
        "timestamp": "2025-05-26T16:00:00",
        "taches": [
            {
                "nom_machine": "Compresseur A3",
                "panne": "Fuite d'huile",
                "tache_effectuee": "Remplacement joint",
                "heure_debut": "08:00",
                "heure_fin": "10:30"
            }
        ],
        "commandes": [
            {
                "reference_piece": "SKF-6205",
                "designation": "Roulement à billes",
                "quantite": "2",
                "urgence": "Normal",
                "commentaire": ""
            }
        ],
        "signature": []
    }
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'status': 'error', 'message': 'Corps JSON manquant ou invalide'}), 400

        # Validation des champs obligatoires
        if not data.get('nom') or not data.get('prenom'):
            return jsonify({'status': 'error', 'message': 'Champs nom et prenom obligatoires'}), 400

        taches    = data.get('taches', [])
        commandes = data.get('commandes', [])
        signature = data.get('signature', [])

        # Normaliser en JSON si ce sont déjà des chaînes
        if isinstance(taches, str):
            taches = json.loads(taches)
        if isinstance(commandes, str):
            commandes = json.loads(commandes)
        if isinstance(signature, str):
            signature = json.loads(signature)

        conn = get_db()
        c = conn.cursor()
        c.execute('''
            INSERT INTO rapports
                (nom, prenom, responsable, departement,
                 heure_debut_journee, heure_fin_journee,
                 date, timestamp, taches, commandes, signature)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('nom', '').strip(),
            data.get('prenom', '').strip(),
            data.get('responsable', '').strip(),
            data.get('departement', '').strip(),
            data.get('heure_debut_journee', '').strip(),
            data.get('heure_fin_journee', '').strip(),
            data.get('date', datetime.now().strftime('%d/%m/%Y')),
            data.get('timestamp', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
            json.dumps(taches,    ensure_ascii=False),
            json.dumps(commandes, ensure_ascii=False),
            json.dumps(signature, ensure_ascii=False),
        ))
        rapport_id = c.lastrowid
        conn.commit()
        conn.close()

        print(f'[RAPPORT] #{rapport_id} reçu — {data.get("nom")} {data.get("prenom")}')
        return jsonify({'status': 'success', 'id': rapport_id,
                        'message': f'Rapport #{rapport_id} enregistré avec succès'})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ── Réception d'une commande de pièce autonome ────────────

@app.route('/api/commande', methods=['POST'])
def receive_commande():
    """
    Reçoit une commande de pièce autonome depuis l'application mobile.

    Corps JSON attendu :
    {
        "technicien": "Jean Dupont",
        "departement": "Maintenance",
        "nom_piece": "Roulement SKF 6205",
        "reference": "SKF-6205-2RS",
        "quantite": "2",
        "urgence": "Urgent",
        "machine": "Compresseur A3",
        "justification": "Usure excessive détectée",
        "date": "26/05/2025 14:30"
    }
    """
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'status': 'error', 'message': 'Corps JSON manquant'}), 400

        conn = get_db()
        c = conn.cursor()
        c.execute('''
            INSERT INTO commandes_standalone
                (technicien, departement, nom_piece, reference,
                 quantite, urgence, machine, justification, date, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            data.get('technicien', '').strip(),
            data.get('departement', '').strip(),
            data.get('nom_piece', '').strip(),
            data.get('reference', '').strip(),
            data.get('quantite', '1').strip(),
            data.get('urgence', 'Normal').strip(),
            data.get('machine', '').strip(),
            data.get('justification', '').strip(),
            data.get('date', datetime.now().strftime('%d/%m/%Y %H:%M')),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        ))
        conn.commit()
        conn.close()

        print(f'[COMMANDE] Pièce "{data.get("nom_piece")}" enregistrée')
        return jsonify({'status': 'success', 'message': 'Commande enregistrée'})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ── Synchronisation pour le logiciel PC ───────────────────

@app.route('/api/sync/<int:last_id>', methods=['GET'])
def sync_rapports(last_id):
    """
    Retourne tous les rapports dont l'ID est supérieur à last_id.
    Le logiciel PC interroge cette route toutes les 5 secondes.
    """
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('''
            SELECT id, nom, prenom, responsable, departement,
                   heure_debut_journee, heure_fin_journee,
                   date, timestamp, taches, commandes, signature
            FROM rapports
            WHERE id > ?
            ORDER BY id ASC
        ''', (last_id,))
        rows = c.fetchall()
        conn.close()

        rapports = [dict(row) for row in rows]

        return jsonify({
            'status': 'success',
            'rapports': rapports,
            'count': len(rapports),
            'last_id': rapports[-1]['id'] if rapports else last_id
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ── Statistiques globales ──────────────────────────────────

@app.route('/api/stats', methods=['GET'])
def get_stats():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) as total FROM rapports')
        total = c.fetchone()['total']
        c.execute("SELECT COUNT(*) as pending FROM commandes_standalone WHERE statut='En attente'")
        pending = c.fetchone()['pending']
        conn.close()
        return jsonify({
            'status': 'success',
            'total_rapports': total,
            'commandes_en_attente': pending,
            'serveur': 'Render',
            'heure': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ──────────────────────────────────────────────────────────
#  LANCEMENT
# ──────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)