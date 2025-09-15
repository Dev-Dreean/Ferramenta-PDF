import re, io, zipfile, tempfile, threading, uuid, os, json, time, shutil, tracemalloc
from pathlib import Path
from flask import Flask, request, send_file, render_template_string, jsonify, Response, after_this_request
from pypdf import PdfReader, PdfWriter
import fitz
from PIL import Image
import webbrowser
import signal

app = Flask(__name__)

tasks = {}
MEMORY_LIMIT_MB = 512

# Padrão Regex (não mais usado ativamente, mas mantido caso precise no futuro)
NAME_PATTERN = re.compile(r"Cadastro:\s*\d+\s*(.*?)\s*CNPJ", re.DOTALL | re.IGNORECASE)

def compress_pdf_with_pymupdf(pdf_bytes):
    """Comprime um PDF usando PyMuPDF para otimizar o tamanho."""
    try:
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        compressed_bytes = pdf_document.tobytes(garbage=4, deflate=True, linear=True)
        pdf_document.close()
        return compressed_bytes
    except Exception as e:
        print(f"Erro na compressão com PyMuPDF: {e}. Retornando arquivo original.")
        return pdf_bytes

HTML = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>PDF Site Pro</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
/* --- Definição de Temas --- */
:root, body.theme-black {
  --bg-main:    #121318;
  --bg-panel:   #1b212b;
  --bg-editor:  #101114;
  --dash:       rgba(255,255,255,0.2);
  --text:       #e0e0e0;
  --text-muted: #8a8f98;
  --accent:     #0d6efd;
  --red:        #dc3545;
  /* Novas Cores Vibrantes */
  --green-light: #3dd578; --green-dark: #28a745;
  --purple-light: #a478f1; --purple-dark: #6f42c1;
  --orange-light: #fdb36a; --orange-dark: #fd7e14;
  --cyan-light: #67d7f5; --cyan-dark: #0dcaf0;
}
body.theme-gray {
  --bg-main:    #495057;
  --bg-panel:   #343a40;
  --bg-editor:  #212529;
  --dash:       rgba(255, 255, 255, 0.25);
  --text:       #f8f9fa;
  --text-muted: #adb5bd;
}
body.theme-white {
  --bg-main:    #f8f9fa;
  --bg-panel:   #ffffff;
  --bg-editor:  #e9ecef;
  --dash:       rgba(0, 0, 0, 0.2);
  --text:       #212529;
  --text-muted: #6c757d;
  --bg-panel-shadow: 0 4px 6px rgba(0,0,0,0.05);
}

* { box-sizing:border-box; margin:0; padding:0; }
html,body {
  height:100%;
  background: var(--bg-main);
  color: var(--text);
  font-family:'Inter',sans-serif;
  overflow:hidden;
  transition: background-color 0.3s, color 0.3s;
}
#container {
  display:grid; grid-template-columns:380px 1fr;
  grid-gap:20px; padding:20px; height:100vh;
  transition: all 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}
aside { display:flex; flex-direction:column; gap:20px; overflow-y:auto; }
.panel {
    background: var(--bg-panel);
    border-radius:8px;
    padding:16px;
    box-shadow: var(--bg-panel-shadow, none);
    transition: all 0.6s cubic-bezier(0.4, 0, 0.2, 1);
    transform-origin: top left;
}

/* --- ESTADO INICIAL (somente painel de Ferramentas central) --- */
/* --- ESTADO INICIAL (somente painel de Ferramentas central) --- */
#container.initial-state {
    display: flex;                /* substitui o grid temporariamente */
    justify-content: center;
    align-items: center;
    padding: 0;
    height: 100vh;
    overflow: hidden !important;
}
#container.initial-state aside { /* Mantém apenas o painel principal visível */
    width: 100%;
    max-width: 1200px;
    display: flex;
    justify-content: center;
    align-items: center;
    overflow: hidden !important;
}
#container.initial-state main { /* Esconde área de visualização enquanto vazio */
    display: none !important;
}
#container.initial-state #drop-area-panel {
    width: 100%;
    max-width: 1100px;
    min-height: 700px;
    transform: none;
    box-shadow: 0 15px 55px rgba(0,0,0,0.55);
    border: 1px solid var(--dash);
    animation: intro-pop .6s ease;
    padding: 80px 90px;
        overflow: hidden !important;
        border-radius: 38px !important;
}
#container.initial-state #drop-area-panel h2 { display: none !important; }
    /* Animação de deslocamento e redimensionamento do painel */
    #container.initial-state #drop-area-panel {
        position: relative;
        left: 0;
        top: 0;
        transition:
            max-width 0.8s cubic-bezier(.4,1.6,.4,1),
            min-height 0.8s cubic-bezier(.4,1.6,.4,1),
            padding 0.8s cubic-bezier(.4,1.6,.4,1),
            border-radius 0.8s cubic-bezier(.4,1.6,.4,1),
            box-shadow 0.8s cubic-bezier(.4,1.6,.4,1),
            left 0.8s cubic-bezier(.4,1.6,.4,1),
            top 0.8s cubic-bezier(.4,1.6,.4,1);
    }
}
@keyframes intro-pop { from { opacity:0; transform:translateY(20px);} to {opacity:1; transform:translateY(0);} }

/* Painéis auxiliares ficam ocultos já pelo .hidden; reforço para inicial */
#container.initial-state #file-list-panel,
#container.initial-state #history-panel,
#container.initial-state #ops-panel { display: none !important; }
/* Esconde checkbox no estado inicial */
#container.initial-state .checkbox { display:none !important; }

.panel.hidden {
    opacity: 0 !important;
    transform: scale(0.97);
    pointer-events: none;
    height: 0;
    padding: 0;
    margin: 0;
    border: none;
    overflow: hidden;
}
/* --- FIM ESTADO INICIAL --- */

.panel h2 { margin-bottom:12px; font-size:1.1rem; }
#drop-area {
    border:3px dashed var(--dash);
    border-radius:38px !important;
    padding:110px 80px; text-align:center;
    color:var(--text-muted);
    transition:background .3s, border-color .3s, transform .3s, border-radius .3s;
    min-height: 600px;
    width: 100%;
    max-width: 1000px;
    display:flex; flex-direction:column; align-items:center; justify-content:center; gap:38px;
    font-size:2.6rem;
    overflow: hidden !important;
}
#container:not(.initial-state) #drop-area-panel {
    max-width: 620px !important;
    min-height: unset !important;
    padding: 16px !important;
    border-radius: 8px !important;
    box-shadow: var(--bg-panel-shadow, none) !important;
        left: 0 !important;
        top: 0 !important;
}
#container:not(.initial-state) #drop-area {
    border-radius: 6px !important;
    padding: 20px !important;
    min-height: unset !important;
    max-width: 100% !important;
    font-size: 1.1rem !important;
    gap: 18px !important;
}
#container:not(.initial-state) #drop-area {
    font-size: 1.1rem !important;
}
#container:not(.initial-state) #select-btn {
    padding: 8px 16px !important;
    font-size: 1rem !important;
    border-radius: 8px !important;
    margin-top: 8px !important;
    box-shadow: 0 4px 12px rgba(0,0,0,0.18) !important;
}
}
}
#drop-area:hover { background:rgba(0,0,0,0.05); }
#drop-area i { font-size:4.2rem; margin-bottom:12px; display:block; opacity:0.9; }
#select-btn {
    margin-top:18px; background:var(--accent); border:none; color:#fff;
    padding:38px 80px; border-radius:28px; cursor:pointer;
    font-size:2.2rem; font-weight:700; letter-spacing:1px;
    box-shadow:0 10px 32px rgba(0,0,0,0.35);
    transition: transform .25s, box-shadow .25s, background .25s;
}
#select-btn:hover { transform: translateY(-4px); box-shadow:0 10px 28px rgba(0,0,0,0.45); }
#select-btn:active { transform: translateY(-1px); box-shadow:0 4px 16px rgba(0,0,0,0.4); }
.checkbox { margin-top:16px; display:flex; align-items:center; gap:8px; font-size:0.9rem; }
.checkbox input { transform:scale(1.2); }
#file-list, #history-list {
  list-style:none; max-height:200px; overflow-y:auto; overflow-x:hidden;
}
#file-list li, #history-list li {
  display:flex; align-items:center; gap:12px; padding:8px;
  border-bottom:1px solid var(--dash);
  transition:background .2s, border-color .3s;
}
#file-list li:hover, #history-list li:hover { background:rgba(0,0,0,0.05); }
body.theme-white #file-list li:hover, body.theme-white #history-list li:hover { background: #f1f3f5; }
#file-list li.active { background:rgba(41,121,255,0.1); }
.file-icon { color:var(--accent); font-size:1.2rem; }
.file-info { display:flex; flex-direction:column; flex:1; gap:4px; min-width:0; }
.file-name { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-weight:500; }
.file-meta { font-size:0.85rem; color:var(--text-muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }

.file-actions { display: flex; align-items: center; gap: 8px; }
.file-actions button {
    background:transparent; border:none; color:var(--text-muted); cursor:pointer;
    font-size:1rem; width: 28px; height: 28px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    transition: color .2s, background-color .2s;
}
.file-actions button:hover { color: #fff; background-color: rgba(255,255,255,0.1); }
.file-actions .remove-btn:hover { background-color: var(--red); }

#ops { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
#ops button {
  padding:12px; border: none; border-radius:8px; color:#fff;
  font-weight:600; cursor:pointer; transition:all .2s ease-in-out; display:flex;
  align-items:center; justify-content:center; gap:8px;
  box-shadow: 0 4px 15px rgba(0,0,0,0.2);
}
#ops button:hover:not(:disabled) { transform: translateY(-3px); box-shadow: 0 6px 20px rgba(0,0,0,0.3); }

#merge-btn      { background-image: linear-gradient(45deg, var(--green-light), var(--green-dark)); }
#split-btn      { background-image: linear-gradient(45deg, var(--purple-light), var(--purple-dark)); }
#img-to-pdf-btn { background-image: linear-gradient(45deg, var(--orange-light), var(--orange-dark)); }
#pdf-to-img-btn { background-image: linear-gradient(45deg, var(--cyan-light), var(--cyan-dark)); }
#clear-btn { background:var(--bg-panel); color:var(--text-muted); grid-column: 1 / -1; border: 2px solid var(--dash); box-shadow: none; }
#clear-btn:hover:not(:disabled) { background: var(--red); color: #fff; border-color: var(--red); transform: none; }
#clear-btn:disabled { opacity: 0.4; cursor: not-allowed; }


main {
  background:var(--bg-panel);
  box-shadow: var(--bg-panel-shadow, none);
  border-radius:8px; padding:16px;
  display:grid; grid-template-rows:auto 1fr; overflow:hidden;
  transition: all 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}
main h2 { grid-row:1; margin-bottom:12px; }
#viewer {
  grid-row:2; position:relative; width:100%; height:100%;
  background:rgba(0,0,0,0.2); border-radius:6px;
  display:flex; align-items:center; justify-content:center; overflow:hidden;
}
#viewer.hidden { display: none !important; }
#viewer canvas { max-width:100%; max-height:100%; display:none; }
#viewer .placeholder { color:var(--text-muted); text-align:center; }
.viewer-controls {
  position:absolute; top:8px; left:50%; transform:translateX(-50%);
  background:rgba(27,33,43,0.8); padding:6px 12px; border-radius:6px;
  display:flex; align-items:center; gap:12px; z-index:10;
}
.viewer-controls button { background:transparent; border:none; color:#fff; cursor:pointer; font-size:1.2rem; }
#editor-view {
    display: none; grid-row: 2;
    background: var(--bg-editor);
    border-radius: 6px; flex-direction: column; overflow: hidden;
    transition: background-color 0.3s;
}
#editor-view.visible { display: flex; }
.editor-toolbar {
    padding: 8px 12px;
    background: rgba(0,0,0,0.2);
    display: flex; align-items: center; gap: 12px;
    flex-shrink: 0;
}
.editor-toolbar button { padding: 8px 12px; border-radius: 5px; border: none; cursor: pointer; font-weight: 600; display: flex; align-items: center; gap: 8px; }
#editor-save-btn { background-color: var(--green-dark); color: #fff; }
#editor-cancel-btn { background-color: var(--purple-dark); color: #fff; }
#editor-delete-selected-btn { background-color: var(--red); color:#fff; display:none; }
#editor-info { margin-left: auto; color: var(--text-muted); font-size: 0.9rem; }
.zoom-control { display:flex; align-items:center; gap:8px; color:var(--text-muted); }
.zoom-control input[type=range] { width: 120px; }
.zoom-control #column-count-label { width: 80px; text-align: right; font-size: 0.9rem;}
#page-thumbnails {
    flex-grow: 1; overflow-y: auto; padding: 16px; display: grid;
    grid-template-columns: repeat(var(--column-count, 8), 1fr);
    gap: 16px;
    align-items: start;
}
.page-thumbnail {
    position: relative; border: 2px solid var(--dash);
    border-radius: 4px; background: var(--bg-panel);
    display: flex; flex-direction: column;
    transition: box-shadow 0.2s, background-color 0.3s, border-color 0.3s;
    user-select: none; cursor: pointer;
}
.page-thumbnail.is-portrait { aspect-ratio: 7 / 10; }
.page-thumbnail.is-landscape { aspect-ratio: 10 / 7; }
.page-thumbnail-inner {
    padding: 12px; width: 100%; height: 100%;
    display: flex; flex-direction: column; align-items: center; gap: 8px;
    position: relative; overflow: hidden;
}
.page-thumbnail canvas {
    flex-grow: 1; max-width: 100%; max-height: 100%;
    object-fit: contain; border-radius: 2px;
    background: #fff;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}
.page-thumbnail.selected { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent); }
.sortable-ghost {
    opacity: 0.4;
    background: var(--accent);
}
.swap-highlight {
    background: var(--accent) !important;
    opacity: 0.6;
}
.page-number { font-size: 0.75rem; font-weight: 600; color: var(--text-muted); flex-shrink: 0; white-space: nowrap; }
.page-controls { position: absolute; top: 4px; right: 4px; display: flex; gap: 4px; z-index: 2; }
.page-controls button {
    background: var(--bg-main); color: var(--text); border: 1px solid var(--dash);
    border-radius: 50%; width: 24px; height: 24px; cursor: pointer; font-size: 0.7rem;
    display: flex; align-items: center; justify-content: center;
    transition: background 0.2s;
}
.page-controls button:hover { background: var(--accent); color: #fff; }
.quick-look-btn {
    position: absolute;
    top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    background: rgba(0,0,0,0.6);
    color: white;
    border: none;
    border-radius: 50%;
    width: 40px; height: 40px;
    font-size: 1.2rem;
    display: flex; align-items: center; justify-content: center;
    opacity: 0;
    transition: opacity 0.2s;
    cursor: pointer;
    z-index: 3;
}
.page-thumbnail:hover .quick-look-btn { opacity: 1; }
.quick-look-btn:hover { background: var(--accent); }

#theme-switcher {
    position: fixed; bottom: 15px; right: 15px;
    background: var(--bg-panel); padding: 8px; border-radius: 20px;
    display: flex; gap: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    border: 1px solid var(--dash); z-index: 1000;
}
.theme-dot {
    width: 20px; height: 20px; border-radius: 50%;
    cursor: pointer; border: 2px solid var(--dash);
    transition: transform 0.2s, border-color 0.2s;
}
.theme-dot:hover { transform: scale(1.1); }
.theme-dot.active { border-color: var(--accent); }

.modal-overlay {
    position: fixed; top: 0; left: 0;
    width: 100%; height: 100%;
    background: rgba(0,0,0,0.7);
    display: flex; align-items: center; justify-content: center;
    z-index: 2000;
    opacity: 0; visibility: hidden;
    transition: opacity 0.2s, visibility 0.2s;
}
.modal-overlay:not(.hidden) {
    opacity: 1; visibility: visible;
}
.modal-content {
    background: var(--bg-panel); padding: 15px;
    border-radius: 8px; max-width: 90vw; max-height: 90vh;
    position: relative; display: flex;
    box-shadow: 0 5px 20px rgba(0,0,0,0.3);
}
.modal-close-btn {
    position: absolute; top: -15px; right: -15px;
    width: 32px; height: 32px; font-size: 1.5rem; font-weight: bold;
    background: var(--bg-main); border: 2px solid var(--dash);
    color: var(--text); border-radius: 50%; cursor: pointer;
    line-height: 28px;
}
#modal-canvas { max-width: 100%; max-height: 100%; object-fit: contain; }

#loadingOverlay {
  position:fixed; top:0; left:0; width:100%; height:100%;
  background:rgba(0,0,0,0.75); z-index:9999;
  display:none; flex-direction:column; align-items:center; justify-content:center;
  backdrop-filter: blur(5px);
}
#loadingBox {
  background: var(--bg-panel); color: var(--text); padding: 25px;
  border-radius: 8px; width: 90%; max-width: 600px;
  box-shadow: 0 5px 20px rgba(0,0,0,0.3); text-align: left;
}
#loading-footer {
    display: flex;
    justify-content: flex-end;
    gap: 10px;
    margin-top: 20px;
}
#loading-footer button {
    padding: 8px 15px;
    border-radius: 5px;
    border: none;
    cursor: pointer;
    font-weight: 600;
}
#cancel-task-btn { background-color: var(--red); color: white; }
#close-overlay-btn { background-color: var(--text-muted); color: var(--bg-main); }

#loadingLog .log-success { color: var(--green-dark); }
#loadingLog .log-error   { color: var(--red); }
#loadingLog .log-info    { color: var(--accent); }

.history-item-complete {
    background: rgba(40, 167, 69, 0.15);
    border-left: 4px solid var(--green-dark);
}
.download-history-btn {
    background-color: var(--green-dark);
    color: #fff;
    border: none;
    border-radius: 5px;
    padding: 6px 12px;
    font-size: 0.85rem;
    font-weight: 600;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    margin-left: auto;
}
</style>
</head>
<body>

<div id="container" class="initial-state">
  <aside>
    <div class="panel" id="drop-area-panel">
      <h2>Ferramentas</h2>
      <div id="drop-area">
        <i class="fa fa-upload"></i><br>
        Arraste seus arquivos ou
        <button id="select-btn">Selecionar Arquivos</button>
        <input type="file" id="file-input" accept=".pdf,.png,.jpg,.jpeg" multiple style="display:none">
      </div>
      <div class="checkbox">
        <input type="checkbox" id="compress-chk" checked>
        <label for="compress-chk">Otimizar/Comprimir arquivos gerados</label>
      </div>
    </div>
    <div class="panel hidden" id="file-list-panel">
      <h2>Arquivos</h2>
      <ul id="file-list"></ul>
    </div>
    <div class="panel hidden" id="ops-panel">
      <div id="ops">
        <button id="merge-btn"><i class="fa fa-arrows-spin"></i> Unificar</button>
        <button id="split-btn"><i class="fa fa-cut"></i> Desmembrar</button>
        <button id="img-to-pdf-btn"><i class="fa-regular fa-file-pdf"></i> IMG &#10142; PDF</button>
        <button id="pdf-to-img-btn"><i class="fa-regular fa-file-image"></i> PDF &#10142; IMG</button>
        <button id="clear-btn"><i class="fa fa-trash"></i> Limpar Tudo</button>
      </div>
    </div>
    <div class="panel hidden" id="history-panel">
      <h2>Histórico da Sessão</h2>
      <ul id="history-list"></ul>
    </div>
  </aside>

  <main>
    <h2 id="main-title">Visualização</h2>
    <div id="viewer" class="hidden">
      <div class="viewer-controls">
        <button id="prevPage" title="Página Anterior"><i class="fa fa-chevron-left"></i></button>
        <span id="pageInfo">0/0</span>
        <button id="nextPage" title="Próxima Página"><i class="fa fa-chevron-right"></i></button>
        <button id="fullscreenBtn" title="Tela Cheia"><i class="fa fa-expand"></i></button>
      </div>
      <canvas id="pdfCanvas"></canvas>
      <div class="placeholder"><i class="fa fa-file-alt" style="font-size:2rem;"></i><br>Selecione um arquivo para visualizar</div>
    </div>
    
    <div id="editor-view">
        <div class="editor-toolbar">
            <button id="editor-save-btn"><i class="fa fa-check"></i> Salvar</button>
            <button id="editor-cancel-btn"><i class="fa fa-times"></i> Cancelar</button>
            <button id="editor-delete-selected-btn"><i class="fa fa-trash-alt"></i> Excluir Selecionadas</button>
            <div class="zoom-control">
                <i class="fa fa-search-minus"></i>
                <input type="range" id="column-zoom-slider" min="4" max="10" value="6" step="1">
                <i class="fa fa-search-plus"></i>
                <span id="column-count-label">8 Colunas</span>
            </div>
            <span id="editor-info">Arraste para reordenar ou trocar.</span>
        </div>
        <div id="page-thumbnails"></div>
    </div>
  </main>
</div>

<div id="theme-switcher">
    <div class="theme-dot" data-theme="black" style="background: #121318;" title="Tema Preto"></div>
    <div class="theme-dot" data-theme="gray" style="background: #495057;" title="Tema Cinza"></div>
    <div class="theme-dot" data-theme="white" style="background: #f8f9fa;" title="Tema Branco"></div>
</div>

<div id="page-preview-modal" class="modal-overlay hidden">
    <div class="modal-content">
        <button class="modal-close-btn">&times;</button>
        <canvas id="modal-canvas"></canvas>
    </div>
</div>

<div id="loadingOverlay">
    <div id="loadingBox">
        <h3 id="loadingTitle"></h3>
        <div id="progress-area" style="margin-bottom: 15px;">
            <div class="progress-bar-container" style="width: 100%; background-color: rgba(0,0,0,0.3); border-radius: 4px; overflow: hidden; height: 12px;">
                <div class="progress-bar" id="progressBar" style="width: 0%; height: 100%; background-color: var(--accent); transition: width 0.2s ease-in-out;"></div>
            </div>
            <div class="progress-text" id="progressText" style="font-size: 0.85rem; color: var(--text-muted); margin-top: 5px; text-align: right;"></div>
        </div>
        <div id="downloadReadyArea" style="display: none; margin-top: 20px; text-align: center;">
            <button id="downloadReadyBtn" style="background-color: var(--green-dark); color: #fff; padding: 12px 25px; font-size: 1.1rem; font-weight: 600; border: none; border-radius: 6px; cursor: pointer;"><i class="fa fa-download"></i> Baixar Arquivo</button>
        </div>
        <button id="toggleLogBtn" data-visible="false" style="background: none; border: none; color: var(--accent); cursor: pointer; font-size: 0.9rem; padding: 5px 0; margin-bottom: 10px;">Mostrar Detalhes <i class="fa fa-chevron-down"></i></button>
        <div id="loadingLog" style="background: rgba(0,0,0,0.3); border-radius: 6px; font-family: 'Courier New', Courier, monospace; font-size: 0.9rem; line-height: 1.5; white-space: pre-wrap; color: var(--text-muted); max-height: 0; overflow-y: auto; transition: max-height 0.3s ease-out; padding: 0;"></div>
        <div id="loading-footer">
            <button id="cancel-task-btn">Cancelar</button>
            <button id="close-overlay-btn">Fechar</button>
        </div>
    </div>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.14.305/pdf.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Sortable/1.15.0/Sortable.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.0/modular/sortable.swap.min.js"></script>

<script>
// --- ELEMENTOS DO DOM ---
const container = document.getElementById('container');
const bodyEl = document.body;
const fileInput = document.getElementById('file-input');
const selectBtn = document.getElementById('select-btn');
const dropArea = document.getElementById('drop-area');
const fileListEl = document.getElementById('file-list');
const historyListEl = document.getElementById('history-list');
const opsPanel = document.getElementById('ops-panel');
const fileListPanel = document.getElementById('file-list-panel');
const historyPanel = document.getElementById('history-panel');
const clearBtn = document.getElementById('clear-btn');
const mainTitle = document.getElementById('main-title');
const viewer = document.getElementById('viewer');
const canvas = document.getElementById('pdfCanvas');
const pageInfo = document.getElementById('pageInfo');
const prevPageBtn = document.getElementById('prevPage');
const nextPageBtn = document.getElementById('nextPage');
const fullscreenBtn = document.getElementById('fullscreenBtn');
const editorView = document.getElementById('editor-view');
const thumbnailsContainer = document.getElementById('page-thumbnails');
const editorSaveBtn = document.getElementById('editor-save-btn');
const editorCancelBtn = document.getElementById('editor-cancel-btn');
const deleteSelectedBtn = document.getElementById('editor-delete-selected-btn');
const zoomSlider = document.getElementById('column-zoom-slider');
const columnCountLabel = document.getElementById('column-count-label');
const themeSwitcher = document.getElementById('theme-switcher');
const modal = document.getElementById('page-preview-modal');
const modalCanvas = document.getElementById('modal-canvas');
const modalCloseBtn = modal.querySelector('.modal-close-btn');
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingLog = document.getElementById('loadingLog');
const toggleLogBtn = document.getElementById('toggleLogBtn');
const cancelTaskBtn = document.getElementById('cancel-task-btn');
const closeOverlayBtn = document.getElementById('close-overlay-btn');
const opsButtons = {
    mergeBtn: document.getElementById('merge-btn'),
    splitBtn: document.getElementById('split-btn'),
    imgToPdfBtn: document.getElementById('img-to-pdf-btn'),
    pdfToImgBtn: document.getElementById('pdf-to-img-btn'),
};


// --- ESTADO DA APLICAÇÃO ---
let files = [], sessionHistory = [], doc = null, currentIdx = null, lastSelectedThumbnail = null, currentTaskId = null;
pdfjsLib.GlobalWorkerOptions.workerSrc = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.14.305/pdf.worker.min.js`;

// --- INICIALIZAÇÃO ---
window.onload = () => {
    Sortable.mount(new Swap());
    const savedTheme = localStorage.getItem('selectedTheme') || 'black';
    applyTheme(savedTheme);
    updateUIState();
    renderHistory();
};

// --- FUNÇÕES DE CONTROLE DA UI ---
function updateUIState() {
    const hasFiles = files.length > 0;
    const pdfCount = files.filter(f => f.file.type === 'application/pdf').length;
    const imgCount = files.filter(f => f.file.type.startsWith('image/')).length;
    // Alterna layout inicial (centralizado) e layout completo (grid)
    container.classList.toggle('initial-state', !hasFiles);
    if (hasFiles) {
        // Garante que o container volte ao grid original
        container.style.display = 'grid';
        container.style.gridTemplateColumns = '380px 1fr';
    } else {
        // Limpa estilos para permitir CSS do estado inicial
        container.removeAttribute('style');
    }

    fileListPanel.classList.toggle('hidden', !hasFiles);
    historyPanel.classList.toggle('hidden', !hasFiles);
    opsPanel.classList.toggle('hidden', !hasFiles);
    
    // Merge requires at least 2 PDFs
    opsButtons.mergeBtn.disabled = pdfCount < 2;
    // Split requires at least 1 PDF
    opsButtons.splitBtn.disabled = pdfCount < 1;
    // Convert images to PDF requires at least 1 image
    opsButtons.imgToPdfBtn.disabled = imgCount < 1;
    // Convert PDF to images requires at least 1 PDF
    opsButtons.pdfToImgBtn.disabled = pdfCount < 1;
    // Mostrar/esconder botões conforme aplicabilidade
    opsButtons.mergeBtn.style.display     = pdfCount >= 2 ? 'flex' : 'none';
    opsButtons.splitBtn.style.display     = pdfCount >= 1 ? 'flex' : 'none';
    opsButtons.imgToPdfBtn.style.display  = imgCount >= 1 ? 'flex' : 'none';
    opsButtons.pdfToImgBtn.style.display  = pdfCount >= 1 ? 'flex' : 'none';
    clearBtn.disabled = !hasFiles;

    if (hasFiles) {
        updateList();
    } else {
        fileListEl.innerHTML = '<li style="color:var(--text-muted); border:none;">Nenhum arquivo adicionado</li>';
        clearViewer();
    }
}


// --- FUNÇÕES DE TEMA ---
function applyTheme(themeName) {
    bodyEl.className = `theme-${themeName}`;
    themeSwitcher.querySelectorAll('.theme-dot').forEach(dot => {
        dot.classList.toggle('active', dot.dataset.theme === themeName);
    });
    localStorage.setItem('selectedTheme', themeName);
}

// --- FUNÇÕES DE ARQUIVOS E HISTÓRICO ---
function addFiles(fileList) {
    const firstTime = files.length === 0;
    for (const f of fileList) {
        const it = { file: f, pages: '?', size: (f.size / 1024 / 1024).toFixed(2) + ' MB' };
        files.push(it);
        if (f.type === 'application/pdf') {
            const reader = new FileReader();
            reader.onload = async () => {
                try {
                    const pdfDoc = await pdfjsLib.getDocument({ data: new Uint8Array(reader.result) }).promise;
                    it.pages = pdfDoc.numPages;
                } catch (e) { it.pages = 'Erro'; }
                if (!firstTime) updateList();
            };
            reader.readAsArrayBuffer(f);
        }
    }
    if(firstTime && fileList.length > 0) {
        updateUIState();
    // Revela o viewer somente após existir ao menos um arquivo
    viewer.classList.remove('hidden');
    } else {
        updateList();
    }
}

function updateList() {
    fileListEl.innerHTML = '';
    files.forEach((it, i) => {
        const li = document.createElement('li');
        if (i === currentIdx) li.classList.add('active');
        const isPdf = it.file.type === 'application/pdf';
        const icon = isPdf ? 'fa-file-pdf' : 'fa-file-image';
        li.innerHTML = `
            <i class="fa-regular ${icon} file-icon"></i>
            <div class="file-info">
                <span class="file-name" title="${it.file.name}">${it.file.name}</span>
                <span class="file-meta">${isPdf ? `${it.pages} Pág - ` : ''}${it.size}</span>
            </div>
            <div class="file-actions">
                ${isPdf ? `<button class="view-btn" title="Visualizar"><i class="fa fa-eye"></i></button>
                           <button class="edit-btn" title="Editar Páginas"><i class="fa fa-pen-to-square"></i></button>` : ''}
                <button class="remove-btn" title="Remover"><i class="fa fa-trash"></i></button>
            </div>
        `;
        if (isPdf) {
            li.querySelector('.view-btn').onclick = () => selectFile(i);
            li.querySelector('.edit-btn').onclick = () => startEditor(i);
        }
        li.querySelector('.remove-btn').onclick = () => {
            files.splice(i, 1);
            if (i === currentIdx) clearViewer(); else if (i < currentIdx) currentIdx--;
            updateUIState();
        };
        fileListEl.appendChild(li);
    });
}

function renderHistory() {
    historyListEl.innerHTML = '';
     if (sessionHistory.length === 0) {
        historyListEl.innerHTML = '<li style="color:var(--text-muted); border:none;">Nenhum item processado</li>';
        return;
    }
    sessionHistory.forEach(item => {
        const li = document.createElement('li');
        li.className = 'history-item-complete';
        li.innerHTML = `
            <i class="fa-regular fa-file-zipper file-icon"></i>
            <div class="file-info">
                 <span class="file-name" title="${item.filename}">${item.filename}</span>
            </div>
            <button class="download-history-btn" data-task-id="${item.taskId}" data-filename="${item.filename}">
                <i class="fa fa-download"></i> Baixar
            </button>
        `;
        historyListEl.appendChild(li);
    });
}

document.addEventListener('click', function(e){
    if(e.target && e.target.closest('.download-history-btn')){
        const btn = e.target.closest('.download-history-btn');
        window.location.href = `/api/download/${btn.dataset.taskId}?filename=${encodeURIComponent(btn.dataset.filename)}`;
    }
});


function selectFile(i) {
    if (i < 0 || i >= files.length || files[i].file.type !== 'application/pdf') return;
    cancelEdit();
    currentIdx = i;
    updateList();
    const reader = new FileReader();
    reader.onload = async () => {
        doc = await pdfjsLib.getDocument({ data: new Uint8Array(reader.result) }).promise;
        renderPage(1);
    };
    reader.readAsArrayBuffer(files[i].file);
}

function renderPage(pageNum) {
    if (!doc) return;
    doc.getPage(pageNum).then(page => {
        const viewport = page.getViewport({ scale: 1.2 });
        canvas.width = viewport.width; canvas.height = viewport.height;
        page.render({ canvasContext: canvas.getContext('2d'), viewport: viewport });
        viewer.querySelector('.placeholder').style.display = 'none';
        canvas.style.display = 'block';
        pageInfo.textContent = `${pageNum}/${doc.numPages}`;
    });
}

function clearViewer() {
    doc = null; currentIdx = null;
    canvas.style.display = 'none';
    viewer.querySelector('.placeholder').style.display = 'block';
    pageInfo.textContent = '0/0';
    const activeLi = fileListEl.querySelector('.active');
    if (activeLi) activeLi.classList.remove('active');
}

// --- FUNÇÕES DO EDITOR E PREVIEW ---
async function startEditor(fileIndex) {
    selectFile(fileIndex);
    mainTitle.textContent = "Editor de Páginas";
    viewer.classList.add('hidden');
    editorView.classList.add('visible');
    
    const sliderValue = parseInt(zoomSlider.value, 10);
    const minSlider = parseInt(zoomSlider.min, 10);
    const maxSlider = parseInt(zoomSlider.max, 10);
    const columnCount = (maxSlider + minSlider) - sliderValue;
    thumbnailsContainer.style.setProperty('--column-count', columnCount);
    columnCountLabel.textContent = `${columnCount} Colunas`;

    const file = files[fileIndex].file;
    const reader = new FileReader();
    reader.onload = async () => {
        const pdfDoc = await pdfjsLib.getDocument({ data: new Uint8Array(reader.result) }).promise;
        thumbnailsContainer.innerHTML = '';
        
        const thumbShells = [];
        for (let i = 1; i <= pdfDoc.numPages; i++) {
            const { thumb } = createThumbnailShell(i);
            thumbnailsContainer.appendChild(thumb);
            thumbShells.push({ thumb, pageNum: i });
        }
        
        new Sortable(thumbnailsContainer, {
            swap: true,
            swapClass: "swap-highlight",
            animation: 500,
            easing: 'cubic-bezier(0.25, 0.46, 0.45, 0.94)',
            ghostClass: 'sortable-ghost'
        });
        
        for (const shell of thumbShells) {
            const page = await pdfDoc.getPage(shell.pageNum);
            await populateThumbnail(shell.thumb, page);
        }
    };
    reader.readAsArrayBuffer(file);
}

function createThumbnailShell(pageNum) {
    const thumb = document.createElement('div');
    thumb.className = 'page-thumbnail';
    thumb.dataset.originalIndex = pageNum - 1;
    thumb.dataset.rotation = 0;
    const innerDiv = document.createElement('div');
    innerDiv.className = 'page-thumbnail-inner';
    const pageCanvas = document.createElement('canvas');
    innerDiv.innerHTML = `
        <span class="page-number">Página ${pageNum}</span>
        <button class="quick-look-btn" title="Visualizar página"><i class="fa fa-eye"></i></button>
        <div class="page-controls">
            <button class="rotate-page-btn" title="Girar 90°"><i class="fa fa-sync-alt"></i></button>
        </div>`;
    innerDiv.insertBefore(pageCanvas, innerDiv.querySelector('.quick-look-btn'));
    thumb.appendChild(innerDiv);
    return { thumb };
}

async function populateThumbnail(thumb, page) {
    const viewport = page.getViewport({ scale: 1 });
    const isPortrait = viewport.height > viewport.width;
    const pageCanvas = thumb.querySelector('canvas');
    thumb.classList.add(isPortrait ? 'is-portrait' : 'is-landscape');
    renderThumbnail(page, pageCanvas, 0);
    thumb.querySelector('.rotate-page-btn').onclick = e => {
        e.stopPropagation();
        let rot = parseInt(thumb.dataset.rotation, 10);
        thumb.dataset.rotation = (rot + 90) % 360;
        renderThumbnail(page, pageCanvas, parseInt(thumb.dataset.rotation, 10));
    };
    thumb.querySelector('.quick-look-btn').onclick = e => {
        e.stopPropagation();
        showPageInModal(page, parseInt(thumb.dataset.rotation, 10));
    };
    thumb.onclick = e => handleThumbnailClick(e, thumb);
}

function renderThumbnail(page, canvas, rotation) {
    const viewport = page.getViewport({ scale: 0.4, rotation });
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    page.render({ canvasContext: canvas.getContext('2d'), viewport });
}

function showPageInModal(page, rotation) {
    modal.classList.remove('hidden');
    const viewportOrig = page.getViewport({ scale: 1, rotation });
    const maxWidth = window.innerWidth * 0.9;
    const maxHeight = window.innerHeight * 0.9;
    const scale = Math.min(maxWidth / viewportOrig.width, maxHeight / viewportOrig.height);
    const viewport = page.getViewport({ scale, rotation });
    modalCanvas.width = viewport.width;
    modalCanvas.height = viewport.height;
    page.render({ canvasContext: modalCanvas.getContext('2d'), viewport: viewport });
}

function hideModal() {
    modal.classList.add('hidden');
    const ctx = modalCanvas.getContext('2d');
    ctx.clearRect(0, 0, modalCanvas.width, modalCanvas.height);
    modalCanvas.width = 0; modalCanvas.height = 0;
}

function handleThumbnailClick(event, thumb) {
    const allThumbs = [...thumbnailsContainer.children];
    if (event.shiftKey && lastSelectedThumbnail) {
        const start = allThumbs.indexOf(lastSelectedThumbnail);
        const end = allThumbs.indexOf(thumb);
        allThumbs.slice(Math.min(start, end), Math.max(start, end) + 1).forEach(t => t.classList.add('selected'));
    } else if (event.ctrlKey || event.metaKey) {
        thumb.classList.toggle('selected');
    } else {
        allThumbs.forEach(t => t.classList.remove('selected'));
        thumb.classList.add('selected');
    }
    lastSelectedThumbnail = thumb;
    updateEditorToolbar();
}

function updateEditorToolbar() {
    const selectedCount = thumbnailsContainer.querySelectorAll('.selected').length;
    deleteSelectedBtn.style.display = selectedCount > 0 ? 'flex' : 'none';
}

function cancelEdit() {
    mainTitle.textContent = "Visualização";
    viewer.classList.remove('hidden');
    editorView.classList.remove('visible');
    thumbnailsContainer.innerHTML = '';
    lastSelectedThumbnail = null;
    updateEditorToolbar();
}

function saveAndProcessEdit() {
    const pages = thumbnailsContainer.querySelectorAll('.page-thumbnail');
    if (pages.length === 0) return alert("Não é possível salvar um PDF sem páginas.");
    const operations = { order: [], rotations: {} };
    pages.forEach(thumb => {
        const originalIndex = parseInt(thumb.dataset.originalIndex, 10);
        const rotation = parseInt(thumb.dataset.rotation, 10);
        operations.order.push(originalIndex);
        if (rotation > 0) operations.rotations[originalIndex] = rotation;
    });
    cancelEdit();
    startTask('edit', [files[currentIdx]], { operations: JSON.stringify(operations) });
}

// --- FUNÇÃO DE TAREFAS (BACKEND) ---
function resetLoadingUI() {
    loadingOverlay.style.display = 'flex';
    document.getElementById('loadingTitle').innerHTML = '<i class="fa fa-spinner fa-spin"></i> Processando...';
    loadingLog.innerHTML = '';
    loadingLog.style.maxHeight = '0'; loadingLog.style.padding = '0';
    toggleLogBtn.innerHTML = 'Mostrar Detalhes <i class="fa fa-chevron-down"></i>';
    toggleLogBtn.dataset.visible = 'false';
    document.getElementById('progressBar').style.width = '0%';
    document.getElementById('progressText').textContent = 'Iniciando...';
    document.getElementById('downloadReadyArea').style.display = 'none';
    cancelTaskBtn.style.display = 'block';
    closeOverlayBtn.style.display = 'none';
}

async function startTask(action, filesToProcess = files, extraData = {}) {
    if (filesToProcess.length === 0) {
        alert('Adicione arquivos para processar.');
        return;
    }
    resetLoadingUI();
    const formData = new FormData();
    filesToProcess.forEach(it => formData.append('files', it.file));
    formData.append('compact', document.getElementById('compress-chk').checked);
    for (const key in extraData) formData.append(key, extraData[key]);
    try {
        const res = await fetch(`/api/start-task/${action}`, { method: 'POST', body: formData });
        if (!res.ok) throw new Error(await res.text());
        const { task_id } = await res.json();
        currentTaskId = task_id;
        const eventSource = new EventSource(`/api/stream-status/${task_id}`);
        eventSource.onmessage = event => {
            const data = JSON.parse(event.data);
            if (data.type === 'progress') {
                document.getElementById('progressBar').style.width = `${(data.current / data.total) * 100}%`;
                document.getElementById('progressText').textContent = `Processando: ${data.current} / ${data.total}`;
            } else {
                const logEntry = document.createElement('div');
                logEntry.className = `log-${data.type}`;
                logEntry.textContent = data.message;
                loadingLog.appendChild(logEntry);
                loadingLog.scrollTop = loadingLog.scrollHeight;
            }
        };
        eventSource.onerror = () => {
             eventSource.close();
             currentTaskId = null;
        };
        eventSource.addEventListener('task_complete', e => {
            eventSource.close();
            currentTaskId = null;
            cancelTaskBtn.style.display = 'none';
            closeOverlayBtn.style.display = 'block';
            const { filename } = JSON.parse(e.data);
            document.getElementById('loadingTitle').innerHTML = '<i class="fa fa-check-circle"></i> Concluído!';
            const downloadArea = document.getElementById('downloadReadyArea');
            const downloadBtn = document.getElementById('downloadReadyBtn');
            downloadArea.style.display = 'block';
            downloadBtn.onclick = () => {
                window.location.href = `/api/download/${task_id}?filename=${encodeURIComponent(filename)}`;
            };
            sessionHistory.push({ taskId: task_id, filename: filename });
            renderHistory();
        });
    } catch (e) {
        alert('Erro: ' + e.message);
        loadingOverlay.style.display = 'none';
    }
}

// --- EVENT LISTENERS ---
dropArea.ondragover = e => { e.preventDefault(); e.currentTarget.style.background = 'rgba(0,0,0,0.05)'; };
dropArea.ondragleave = e => e.currentTarget.style.background = '';
dropArea.ondrop = e => { e.preventDefault(); e.stopPropagation(); addFiles(Array.from(e.dataTransfer.files)); };
selectBtn.onclick = () => fileInput.click();
fileInput.onchange = () => { addFiles(Array.from(fileInput.files)); fileInput.value = ''; };
clearBtn.onclick = () => { files = []; sessionHistory = []; updateUIState(); renderHistory(); };

opsButtons.mergeBtn.onclick = () => startTask('merge');
opsButtons.splitBtn.onclick = () => startTask('split');
opsButtons.imgToPdfBtn.onclick = () => startTask('img2pdf');
opsButtons.pdfToImgBtn.onclick = () => startTask('pdf2img');

prevPageBtn.onclick = () => { if (doc && currentPage > 1) renderPage(--currentPage); };
nextPageBtn.onclick = () => { if (doc && currentPage < doc.numPages) renderPage(++currentPage); };
fullscreenBtn.onclick = () => { if (!document.fullscreenElement) viewer.requestFullscreen(); else document.exitFullscreen(); };
editorSaveBtn.onclick = saveAndProcessEdit;
editorCancelBtn.onclick = cancelEdit;
deleteSelectedBtn.onclick = () => {
    thumbnailsContainer.querySelectorAll('.selected').forEach(thumb => thumb.remove());
    updateEditorToolbar();
};
zoomSlider.oninput = () => {
    const sliderValue = parseInt(zoomSlider.value, 10);
    const minSlider = parseInt(zoomSlider.min, 10);
    const maxSlider = parseInt(zoomSlider.max, 10);
    const columnCount = (maxSlider + minSlider) - sliderValue;
    columnCountLabel.textContent = `${columnCount} Colunas`;
    thumbnailsContainer.style.setProperty('--column-count', columnCount);
};
themeSwitcher.onclick = e => {
    if (e.target.classList.contains('theme-dot')) applyTheme(e.target.dataset.theme);
};
toggleLogBtn.onclick = () => {
    const isVisible = toggleLogBtn.dataset.visible === 'true';
    loadingLog.style.maxHeight = isVisible ? '0' : '250px';
    loadingLog.style.padding = isVisible ? '0' : '15px';
    toggleLogBtn.dataset.visible = !isVisible;
};
modalCloseBtn.onclick = hideModal;
modal.onclick = (e) => { if(e.target === modal) hideModal(); };
document.addEventListener('keydown', (e) => { if(e.key === "Escape") hideModal(); });

closeOverlayBtn.onclick = () => loadingOverlay.style.display = 'none';
cancelTaskBtn.onclick = () => {
    if (currentTaskId) {
        fetch(`/api/cancel-task/${currentTaskId}`);
        loadingOverlay.style.display = 'none';
        currentTaskId = null;
    }
};

</script>
</body>
</html>
"""

# Restante do código Python (Flask) permanece o mesmo.
# O código abaixo é idêntico ao anterior, mas está incluído para garantir que o arquivo seja completo.

def run_task_with_memory_limit(task_id, target_func, args):
    tracemalloc.start()
    tracemalloc.clear_traces()
    try:
        if tasks.get(task_id, {}).get('cancelled'):
            log_message(task_id, "Tarefa cancelada antes de iniciar.", "error")
            return
        target_func(*args)
        current, peak = tracemalloc.get_traced_memory()
        peak_mb = peak / 1024 / 1024
        log_message(task_id, f"Pico de memória utilizado: {peak_mb:.2f} MB", "info")
        if peak_mb > MEMORY_LIMIT_MB:
            tasks[task_id]["status"] = "error"
            log_message(task_id, f"ERRO: Limite de memória de {MEMORY_LIMIT_MB} MB excedido.", "error")
    except Exception as e:
        if not tasks.get(task_id, {}).get('cancelled'):
            tasks[task_id]["status"] = "error"
            log_message(task_id, f"Erro fatal na tarefa: {e}", "error")
    finally:
        tracemalloc.stop()

@app.route("/api/start-task/<action>", methods=["POST"])
def start_task(action):
    task_id = str(uuid.uuid4())
    files = request.files.getlist("files")
    compact = request.form.get("compact") == "true"
    if not files: return jsonify({"error": "Nenhum arquivo enviado"}), 400
    task_dir = Path(tempfile.gettempdir()) / task_id
    task_dir.mkdir()
    saved_files = []
    from werkzeug.utils import secure_filename
    for f in files:
        safe_filename = secure_filename(f.filename)
        filepath = task_dir / safe_filename
        f.save(filepath)
        saved_files.append(str(filepath))
    tasks[task_id] = {"status": "running", "log": [], "result_path": None, "result_filename": None, "log_cursor": 0, "cancelled": False}
    task_args = (task_id, saved_files, compact)
    if action == 'edit':
        operations = request.form.get("operations")
        task_args = (task_id, saved_files, compact, operations)
    task_map = {"merge": run_merge_task, "split": run_split_task, "img2pdf": run_img2pdf_task, "pdf2img": run_pdf2img_task, "edit": run_edit_task}
    target_func = task_map.get(action)
    if not target_func: return jsonify({"error": "Ação desconhecida"}), 400
    thread = threading.Thread(target=run_task_with_memory_limit, args=(task_id, target_func, task_args))
    thread.start()
    return jsonify({"task_id": task_id})

@app.route("/api/cancel-task/<task_id>")
def cancel_task(task_id):
    if task_id in tasks:
        tasks[task_id]['cancelled'] = True
        log_message(task_id, "Cancelamento solicitado pelo usuário...", "info")
        return jsonify({"status": "cancel requested"}), 200
    return jsonify({"error": "task not found"}), 404

@app.route("/api/stream-status/<task_id>")
def stream_status(task_id):
    def generate():
        while True:
            task = tasks.get(task_id)
            if not task: break
            while task["log_cursor"] < len(task["log"]):
                yield f'data: {json.dumps(task["log"][task["log_cursor"]])}\n\n'
                task["log_cursor"] += 1
            if task["status"] in ["complete", "error"] or task.get("cancelled"):
                if task["status"] == "complete" and not task.get("cancelled"):
                    payload = {"filename": task.get("result_filename", "download.zip")}
                    yield f'event: task_complete\ndata: {json.dumps(payload)}\n\n'
                break
            time.sleep(0.1)
    return Response(generate(), mimetype="text/event-stream")

@app.route("/api/download/<task_id>")
def download_result(task_id):
    task = tasks.get(task_id)
    filename = request.args.get('filename', 'resultado.zip')
    if not task or not task.get("result_path"): return "Tarefa não encontrada.", 404
    result_path = task["result_path"]
    # Cleanup foi removido para o histórico funcionar
    return send_file(result_path, as_attachment=True, download_name=filename)

def delete_task_files(task_dir_path, task_id):
    time.sleep(5)
    try:
        shutil.rmtree(task_dir_path)
        if task_id in tasks: del tasks[task_id]
        print(f"Limpeza da tarefa {task_id} concluída.")
    except Exception as e:
        print(f"Erro na limpeza da tarefa {task_id}: {e}")

def log_message(task_id, message, type="info"):
    if task_id in tasks: tasks[task_id]["log"].append({"type": type, "message": message})

def log_progress(task_id, current, total):
    if task_id in tasks: tasks[task_id]["log"].append({"type": "progress", "current": current, "total": total})

# --- Funções de Tarefa Modificadas para Suportar Cancelamento ---

def run_edit_task(task_id, file_paths, compact, operations_json):
    try:
        if tasks.get(task_id, {}).get('cancelled'): return
        source_path = file_paths[0]
        task_dir = Path(source_path).parent
        log_message(task_id, f"Iniciando edição: {Path(source_path).name}")
        ops = json.loads(operations_json)
        page_order, rotations = ops.get('order', []), {int(k): v for k, v in ops.get('rotations', {}).items()}
        if not page_order: raise ValueError("Nenhuma página selecionada.")
        source_doc, new_doc = fitz.open(source_path), fitz.open()
        for i, original_page_index in enumerate(page_order):
            if tasks.get(task_id, {}).get('cancelled'): raise Exception("Tarefa cancelada.")
            new_doc.insert_pdf(source_doc, from_page=original_page_index, to_page=original_page_index)
            rotation = rotations.get(original_page_index, 0)
            if rotation > 0: new_doc[-1].set_rotation(rotation)
            log_progress(task_id, i + 1, len(page_order))
        source_doc.close()
        if tasks.get(task_id, {}).get('cancelled'): raise Exception("Tarefa cancelada.")
        pdf_bytes = new_doc.tobytes(garbage=4, deflate=True)
        new_doc.close()
        if compact:
            pdf_bytes = compress_pdf_with_pymupdf(pdf_bytes)
        output_filename = f"{Path(source_path).stem}_editado.pdf"
        final_path = task_dir / output_filename
        with open(final_path, "wb") as f: f.write(pdf_bytes)
        tasks[task_id].update({"result_path": str(final_path), "result_filename": output_filename, "status": "complete"})
        log_message(task_id, "Edição concluída!", "success")
    except Exception as e: 
        if "cancelada" in str(e): log_message(task_id, "Operação cancelada pelo usuário.", "error")
        else: raise e

def run_img2pdf_task(task_id, file_paths, compact):
    try:
        log_message(task_id, f"Convertendo {len(file_paths)} imagens para PDF...")
        task_dir = Path(file_paths[0]).parent
        images = []
        for i, p in enumerate(file_paths):
            if tasks.get(task_id, {}).get('cancelled'): raise Exception("Tarefa cancelada.")
            images.append(Image.open(p).convert('RGB'))
            log_progress(task_id, i + 1, len(file_paths))
        if not images: raise ValueError("Nenhuma imagem válida.")
        output_filename = "IMAGENS_CONVERTIDAS.pdf"
        final_path = task_dir / output_filename
        images[0].save(str(final_path), save_all=True, append_images=images[1:])
        if compact:
            with open(final_path, 'rb') as f: pdf_bytes = f.read()
            pdf_bytes = compress_pdf_with_pymupdf(pdf_bytes)
            with open(final_path, 'wb') as f: f.write(pdf_bytes)
        tasks[task_id].update({"result_path": str(final_path), "result_filename": output_filename, "status": "complete"})
        log_message(task_id, "Conversão concluída!", "success")
    except Exception as e: 
        if "cancelada" in str(e): log_message(task_id, "Operação cancelada pelo usuário.", "error")
        else: raise e

def run_pdf2img_task(task_id, file_paths, compact):
    # Lógica atualizada para processar múltiplos arquivos em pastas
    try:
        task_dir = Path(file_paths[0]).parent
        output_filename = "PDFs_convertidos_para_IMG.zip"
        zip_path = task_dir / output_filename
        total_pages = 0
        for pdf_path in file_paths:
             if tasks.get(task_id, {}).get('cancelled'): raise Exception("Tarefa cancelada.")
             with fitz.open(pdf_path) as doc:
                total_pages += len(doc)
        log_message(task_id, f"Convertendo {total_pages} páginas de {len(file_paths)} PDFs...")
        pages_processed = 0
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for pdf_path in file_paths:
                if tasks.get(task_id, {}).get('cancelled'): raise Exception("Tarefa cancelada.")
                base_name = Path(pdf_path).stem
                doc = fitz.open(pdf_path)
                log_message(task_id, f"Processando '{base_name}.pdf'...")
                for i, page in enumerate(doc):
                    if tasks.get(task_id, {}).get('cancelled'): raise Exception("Tarefa cancelada.")
                    pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72))
                    zf.writestr(f"{base_name}/pagina_{i+1}.jpg", pix.tobytes("jpeg"))
                    pages_processed += 1
                    log_progress(task_id, pages_processed, total_pages)
                doc.close()
        tasks[task_id].update({"result_path": str(zip_path), "result_filename": output_filename, "status": "complete"})
        log_message(task_id, "Conversão concluída!", "success")
    except Exception as e: 
        if "cancelada" in str(e): log_message(task_id, "Operação cancelada pelo usuário.", "error")
        else: raise e

def run_merge_task(task_id, file_paths, compact):
    try:
        log_message(task_id, f"Unificando {len(file_paths)} arquivos...")
        task_dir = Path(file_paths[0]).parent
        writer = PdfWriter()
        for i, path in enumerate(file_paths):
            if tasks.get(task_id, {}).get('cancelled'): raise Exception("Tarefa cancelada.")
            writer.append(path)
            log_progress(task_id, i + 1, len(file_paths))
        buffer = io.BytesIO()
        writer.write(buffer)
        pdf_bytes = buffer.getvalue()
        writer.close()
        if compact:
            pdf_bytes = compress_pdf_with_pymupdf(pdf_bytes)
        output_filename = "PDF_UNIFICADOS.pdf"
        final_path = task_dir / output_filename
        with open(final_path, "wb") as f: f.write(pdf_bytes)
        tasks[task_id].update({"result_path": str(final_path), "result_filename": output_filename, "status": "complete"})
        log_message(task_id, "Unificação concluída!", "success")
    except Exception as e: 
        if "cancelada" in str(e): log_message(task_id, "Operação cancelada pelo usuário.", "error")
        else: raise e

def run_split_task(task_id, file_paths, compact):
    # Lógica atualizada para criar pastas no ZIP
    try:
        total_pages = 0
        for path in file_paths:
            if tasks.get(task_id, {}).get('cancelled'): raise Exception("Tarefa cancelada.")
            with open(path, 'rb') as f:
                reader = PdfReader(f)
                total_pages += len(reader.pages)
        log_message(task_id, f"Desmembrando {total_pages} páginas...")
        task_dir = Path(file_paths[0]).parent
        output_filename = "PDF_DESMEMBRADOS.zip"
        zip_path = task_dir / output_filename
        pages_processed = 0
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in file_paths:
                if tasks.get(task_id, {}).get('cancelled'): raise Exception("Tarefa cancelada.")
                base_name = Path(path).stem
                reader = PdfReader(path)
                log_message(task_id, f"Processando '{base_name}.pdf'...")
                for j, page in enumerate(reader.pages):
                    if tasks.get(task_id, {}).get('cancelled'): raise Exception("Tarefa cancelada.")
                    writer = PdfWriter()
                    writer.add_page(page)
                    buffer = io.BytesIO()
                    writer.write(buffer)
                    pdf_bytes = buffer.getvalue()
                    if compact: pdf_bytes = compress_pdf_with_pymupdf(pdf_bytes)
                    zf.writestr(f"{base_name}/pagina_{j+1}.pdf", pdf_bytes)
                    pages_processed += 1
                    log_progress(task_id, pages_processed, total_pages)
        tasks[task_id].update({"result_path": str(zip_path), "result_filename": output_filename, "status": "complete"})
        log_message(task_id, "Desmembramento concluído!", "success")
    except Exception as e: 
        if "cancelada" in str(e): log_message(task_id, "Operação cancelada pelo usuário.", "error")
        else: raise e

@app.route("/")
def index():
    return render_template_string(HTML)

if __name__ == "__main__":
    import threading, webbrowser, time
    from flask import request

    def run_app():
        app.run(host="127.0.0.1", port=8000, debug=False, use_reloader=False, threaded=True)

    def open_browser():
        time.sleep(1) 
        webbrowser.open("http://127.0.0.1:8000")

    flask_thread = threading.Thread(target=run_app, daemon=True)
    flask_thread.start()
    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()
    
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        print("Encerrando o servidor...")