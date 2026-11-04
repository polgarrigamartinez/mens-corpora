import pandas as pd
import sqlite3
import os
import re

def extraer_anio(val):
    if pd.isna(val):
        return '—'
    s = str(val).strip()
    match = re.search(r'\b(18\d\d|19\d\d)\b', s)
    if match:
        return match.group(1)
    return '—'

def buscar_archivo(lista_nombres):
    home = os.path.expanduser('~')
    carpetas = [
        os.getcwd(),
        os.path.join(home, 'Desktop'),
        os.path.join(home, 'OneDrive', 'Desktop')
    ]
    
    for c in carpetas:
        if os.path.exists(c):
            for nombre in lista_nombres:
                candidato = os.path.join(c, nombre)
                if os.path.exists(candidato):
                    return candidato
    return None

print("--- 1. CARGANDO TÍTULOS, AUTORES Y AÑOS DESDE LOS EXCELS ---")

archivos_excel = {
    'Mentes': ['mentes02_11_2026.xlsx', 'mentes11_10_2026_2.xlsx', 'mentes11_10_2026.xlsx'],
    'Demens': ['demens02_11_2026.xlsx', 'demens18_10_2026.xlsx'],
    'Es Contraste': ['es_contraste02_11_2026.xlsx', 'es_contraste.xlsx'],
    'De Contraste': ['de_contraste02_11_2026.xlsx', 'de_contraste.xlsx']
}

mapa_obras = {}

for subcorpus_nombre, posibles_nombres in archivos_excel.items():
    ruta_excel = buscar_archivo(posibles_nombres)
    if ruta_excel:
        df_excel = pd.read_excel(ruta_excel)
        cargados = 0
        for _, fila in df_excel.iterrows():
            id_txt = str(fila.get('id del archivo', '')).strip().lower()
            titulo_obra = str(fila.get('Título', '')).strip()
            autor_obra = str(fila.get('Autor / Director', fila.get('Autor/Director', fila.get('Autor', '—')))).strip()
            anio_obra = extraer_anio(fila.get('Año', ''))
            
            if id_txt and id_txt != 'nan':
                mapa_obras[id_txt] = {
                    'titulo': titulo_obra,
                    'autor': autor_obra if autor_obra and autor_obra.lower() != 'nan' else '—',
                    'anio': anio_obra
                }
                cargados += 1
        print(f"  ✓ {subcorpus_nombre}: {cargados} obras cargadas desde {os.path.basename(ruta_excel)}")

print(f"Total de obras mapeadas en catálogo: {len(mapa_obras):,}\n")

# Localizar CSV con textos
ruta_csv = buscar_archivo(['corpus_global_completo.csv', 'corpus_global_procesado.csv'])

if not ruta_csv:
    print("❌ ERROR: No se encuentra 'corpus_global_completo.csv'.")
    exit()

print(f"--- 2. CARGANDO TEXTOS DESDE {os.path.basename(ruta_csv)} ---")
df_csv = pd.read_csv(ruta_csv, encoding='utf-8-sig')
print(f"Filas leídas del CSV: {len(df_csv):,}")

# Detectar automáticamente la columna del texto
posibles_cols_texto = ['Texto_Limpio', 'texto_limpio', 'Texto', 'texto', 'contenido', 'Texto_Procesado']
col_texto_hallada = None

for col in posibles_cols_texto:
    if col in df_csv.columns:
        col_texto_hallada = col
        break

if not col_texto_hallada:
    largos = {c: df_csv[c].astype(str).str.len().mean() for c in df_csv.columns}
    col_texto_hallada = max(largos, key=largos.get)

print(f"  👉 Columna seleccionada para el texto: '{col_texto_hallada}'\n")

# Eliminar base de datos previa
directorio_salida = os.path.dirname(ruta_csv)
ruta_db = os.path.join(directorio_salida, 'corpus.db')

if os.path.exists(ruta_db):
    try:
        os.remove(ruta_db)
    except PermissionError:
        print("⚠️ Cierra cualquier programa que esté usando 'corpus.db'.")
        exit()

# Crear SQLite FTS5 con las columnas titulo, autor, anio
conn = sqlite3.connect(ruta_db)
cursor = conn.cursor()

print("Creando tabla FTS5 en SQLite con columna 'autor'...")
cursor.execute('''
    CREATE VIRTUAL TABLE corpus_fts USING fts5(
        subcorpus,
        id_archivo,
        titulo,
        autor,
        anio,
        texto_limpio,
        tokenize = 'unicode61'
    )
''')

registros = []
for idx, fila in df_csv.iterrows():
    col_texto_val = fila.get(col_texto_hallada, '')
    col_sub = fila.get('Subcorpus', fila.get('subcorpus', 'General'))
    col_id = fila.get('id del archivo', fila.get('id_archivo', fila.get('ID_Normalizado', f'doc_{idx}')))
    
    id_clean = str(col_id).strip().lower()
    datos_obra = mapa_obras.get(id_clean, {'titulo': '—', 'autor': '—', 'anio': '—'})

    registros.append((
        str(col_sub) if pd.notna(col_sub) else "General",
        str(col_id) if pd.notna(col_id) else "—",
        str(datos_obra['titulo']) if datos_obra['titulo'] != 'nan' else "—",
        str(datos_obra['autor']) if datos_obra['autor'] != 'nan' else "—",
        str(datos_obra['anio']) if datos_obra['anio'] != 'nan' else "—",
        str(col_texto_val) if pd.notna(col_texto_val) else ""
    ))

cursor.executemany('INSERT INTO corpus_fts VALUES (?, ?, ?, ?, ?, ?)', registros)
conn.commit()

# Comprobación
cursor.execute("SELECT COUNT(*) FROM corpus_fts WHERE length(texto_limpio) > 0")
llenos = cursor.fetchone()[0]

cursor.execute("SELECT subcorpus, titulo, autor, anio FROM corpus_fts WHERE corpus_fts MATCH 'mente'")
prueba = cursor.fetchall()

conn.close()

print("--------------------------------------------------")
print(f"✅ BASE DE DATOS REGENERADA CON ÉXITO")
print(f"   - Documentos con texto cargado: {llenos:,} de {len(df_csv):,}")
print(f"   - Prueba de búsqueda ('mente'): {len(prueba):,} coincidencias.")
if prueba:
    print(f"   - Muestra: Obra '{prueba[0][1]}' | Autor: '{prueba[0][2]}' ({prueba[0][3]})")