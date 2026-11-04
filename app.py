from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import re

app = Flask(__name__)
CORS(app)

def obtener_ruta_db():
    dir_actual = os.path.dirname(os.path.abspath(__file__))
    ruta_directa = os.path.join(dir_actual, 'corpus.db')
    if os.path.exists(ruta_directa):
        return ruta_directa
    home = os.path.expanduser('~')
    candidatos = [
        os.path.join(home, 'Desktop', 'corpus.db'),
        os.path.join(home, 'OneDrive', 'Desktop', 'corpus.db')
    ]
    for c in candidatos:
        if os.path.exists(c):
            return c
    return ruta_directa

RUTA_DB = obtener_ruta_db()

def buscar_kwic_db(palabra_buscada, subcorpus_filtro=None, ventana=7, limite=5000):
    palabra_buscada = palabra_buscada.lower().strip()
    if not palabra_buscada or not os.path.exists(RUTA_DB):
        return []

    # Parsear lista de subcorpus seleccionados
    if isinstance(subcorpus_filtro, str):
        subcorpus_list = [s.strip() for s in subcorpus_filtro.split(',') if s.strip()]
    elif isinstance(subcorpus_filtro, list):
        subcorpus_list = subcorpus_filtro
    else:
        subcorpus_list = ["Todos"]

    conn = sqlite3.connect(RUTA_DB)
    cursor = conn.cursor()
    
    # Si incluye "Todos", lista vacía o se seleccionan los 4, busca en todo el corpus
    if not subcorpus_list or "Todos" in subcorpus_list or len(subcorpus_list) >= 4:
        query = "SELECT subcorpus, id_archivo, titulo, autor, anio, texto_limpio FROM corpus_fts WHERE corpus_fts MATCH ?"
        cursor.execute(query, (f'"{palabra_buscada}"',))
    else:
        placeholders = ', '.join(['?'] * len(subcorpus_list))
        query = f"SELECT subcorpus, id_archivo, titulo, autor, anio, texto_limpio FROM corpus_fts WHERE subcorpus IN ({placeholders}) AND corpus_fts MATCH ?"
        params = tuple(subcorpus_list) + (f'"{palabra_buscada}"',)
        cursor.execute(query, params)
        
    filas = cursor.fetchall()
    conn.close()

    resultados = []
    patron = re.compile(rf'\b{re.escape(palabra_buscada)}\b', re.IGNORECASE)

    for subcorpus, id_archivo, titulo, autor, anio, texto in filas:
        tokens = texto.split()
        posiciones = [i for i, t in enumerate(tokens) if patron.search(t)]

        for pos in posiciones:
            inicio = max(0, pos - ventana)
            fin = min(len(tokens), pos + ventana + 1)

            resultados.append({
                'subcorpus': subcorpus,
                'id_archivo': id_archivo,
                'titulo': titulo,
                'autor': autor,
                'anio': anio,
                'contexto_izq': " ".join(tokens[inicio:pos]),
                'palabra_clave': tokens[pos],
                'contexto_der': " ".join(tokens[pos+1:fin])
            })
            if len(resultados) >= limite:
                break
        if len(resultados) >= limite:
            break

    return resultados

@app.route('/api/buscar', methods=['GET'])
def api_buscar():
    palabra = request.args.get('q', '')
    
    subcorpus_args = request.args.getlist('subcorpus')
    if len(subcorpus_args) == 1 and ',' in subcorpus_args[0]:
        subcorpus_filtro = [s.strip() for s in subcorpus_args[0].split(',') if s.strip()]
    elif subcorpus_args:
        subcorpus_filtro = subcorpus_args
    else:
        subcorpus_filtro = request.args.get('subcorpus', 'Todos')

    try:
        ventana = int(request.args.get('ventana', 7))
    except ValueError:
        ventana = 7

    if not palabra:
        return jsonify({'error': 'Proporciona un término de búsqueda'}), 400
    
    resultados = buscar_kwic_db(palabra, subcorpus_filtro=subcorpus_filtro, ventana=ventana)
    
    distribucion = {}
    for r in resultados:
        sub = r['subcorpus']
        distribucion[sub] = distribucion.get(sub, 0) + 1

    return jsonify({
        'total': len(resultados),
        'distribucion': distribucion,
        'resultados': resultados
    })

if __name__ == '__main__':
    app.run(port=5000, debug=True)