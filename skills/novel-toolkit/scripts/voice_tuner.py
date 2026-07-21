#!/usr/bin/env python3
import argparse, json, os, re, subprocess, sys, threading, time, traceback, shutil
from pathlib import Path
from flask import Flask, jsonify, request, send_file
from gradio_client import Client, handle_file

DEFAULT_PORT = 8900
SCRIPT_DIR = Path(__file__).parent.resolve()

with open(SCRIPT_DIR / 'tuner_page.html', encoding='utf-8') as f:
    HTML_PAGE = f.read()

app = Flask(__name__)

STATE = {
    'target': None, 'vox_url': 'http://localhost:8808', 'tts_client': None, 'roles': [],
    'params': {'cfg': 2.0, 'dit_steps': 10, 'denoise': False, 'normalize': False, 'use_ultimate_clone': False},
    'running': True, 'task_queue': [], 'task_index': 0, 'task_lock': threading.Lock(),
}

def kill_port(port):
    """杀掉占用指定端口的进程（Windows）"""
    try:
        out = subprocess.check_output(
            f'netstat -ano | findstr :{port}', shell=True, text=True
        )
        pids = set()
        for line in out.strip().split('\n'):
            parts = line.strip().split()
            if parts and parts[-1].isdigit():
                pid = parts[-1]
                if pid != '0':
                    pids.add(pid)
        for pid in pids:
            subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True)
            print(f'[voice_tuner] killed PID {pid} on port {port}')
    except subprocess.CalledProcessError:
        pass  # 端口空闲
    except Exception as e:
        print(f'[voice_tuner] kill_port warning: {e}')

def get_client():
    if STATE['tts_client'] is None: STATE['tts_client'] = Client(STATE['vox_url'])
    return STATE['tts_client']

def call_vox(text, ci='', ref=None, **kw):
    c = get_client()
    r = c.predict(text=text, control_instruction=ci, ref_wav=handle_file(ref) if ref else None,
        use_prompt_text=kw.get('use_ultimate_clone', False),
        prompt_text_value=text if kw.get('use_ultimate_clone') else '',
        cfg_value=kw.get('cfg', 2.0), do_normalize=kw.get('normalize', False),
        denoise=kw.get('denoise', False), dit_steps=kw.get('dit_steps', 10), api_name='/generate')
    if isinstance(r, tuple) and len(r) >= 2: return str(r[1])
    if isinstance(r, str): return r
    if isinstance(r, list) and r: return str(r[0])
    raise RuntimeError(f'bad result: {type(r)}')

def fdur(fp):
    return float(subprocess.check_output(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', fp],
        text=True).strip())

P = re.compile(r'^(.+?)\s*[(（]\s*(.*?)\s*[)）]\s*[：:]\s*(.+)$')
S = re.compile(r'^(.+?)\s*[：:]\s*(.+)$')

def parse_vs(fp):
    ls = []
    with open(fp, 'r', encoding='utf-8-sig') as f:
        for ln in f:
            ln = ln.strip()
            if not ln: continue
            m = P.match(ln)
            if m: ls.append({'role': m.group(1).strip(), 'desc': m.group(2).strip(), 'text': m.group(3).strip()}); continue
            m = S.match(ln)
            if m: ls.append({'role': m.group(1).strip(), 'desc': None, 'text': m.group(2).strip()}); continue
            ls.append({'role': '\u65c1\u767d', 'desc': None, 'text': ln})
    return ls

def scan_refs(d):
    r = {}
    if not d.exists(): return r
    for f in d.iterdir():
        if f.suffix.lower() in ('.wav', '.mp3', '.flac', '.ogg'):
            n = f.stem
            if '_ref' in n: n = n[:n.rindex('_ref')]
            r[n] = str(f.resolve())
    return r

def load_roles(target):
    sp = target / 'bible' / 'voices_script.txt'
    ad = target / 'tts_output' / 'auto_refs'
    ad.mkdir(parents=True, exist_ok=True)
    if not sp.exists(): return []
    vs = parse_vs(str(sp))
    refs = scan_refs(ad)
    roles = []
    for v in vs:
        ap = refs.get(v['role'])
        dur = fdur(ap) if ap else None
        roles.append({'role': v['role'], 'desc': v['desc'] or '', 'text': v.get('text', ''), 'audio_path': ap, 'duration': round(dur, 1) if dur else None})
    return roles

def save_vs():
    t = Path(STATE['target'])
    sp = t / 'bible' / 'voices_script.txt'
    lines = []
    for r in STATE['roles']:
        if r.get('desc'): lines.append(f'{r["role"]}({r["desc"]})\uff1a{r.get("text","")}')
        else: lines.append(f'{r["role"]}\uff1a{r.get("text","")}')
    sp.write_text('\n'.join(lines) + '\n', encoding='utf-8')

@app.route('/')
def index(): return HTML_PAGE

@app.route('/api/roles')
def a_roles(): return jsonify(STATE['roles'])

@app.route('/api/audio/<role>')
def a_audio(role):
    for r in STATE['roles']:
        if r['role'] == role and r.get('audio_path'): return send_file(r['audio_path'], mimetype='audio/wav')
    return '', 404

@app.route('/api/params', methods=['GET', 'POST'])
def a_params():
    if request.method == 'POST':
        d = request.get_json()
        for k in ('cfg', 'dit_steps', 'denoise', 'normalize', 'use_ultimate_clone'):
            if k in d: STATE['params'][k] = d[k]
        return jsonify({'ok': True})
    return jsonify(STATE['params'])

@app.route('/api/settings')
def a_settings():
    return jsonify({'vox_url': STATE['vox_url'], 'target': str(STATE['target']) if STATE['target'] else None})

@app.route('/api/settings/url', methods=['POST'])
def a_url():
    d = request.get_json()
    nu = d.get('url', '').strip()
    if nu and nu != STATE['vox_url']: STATE['vox_url'] = nu; STATE['tts_client'] = None
    return jsonify({'ok': True, 'url': STATE['vox_url']})

@app.route('/api/import', methods=['POST'])
def a_import():
    try:
        role = request.form.get('role')
        file = request.files.get('file')
        if not role or not file: return jsonify({'error': 'missing role or file'}), 400
        ad = Path(STATE['target']) / 'tts_output' / 'auto_refs'
        ad.mkdir(parents=True, exist_ok=True)
        tmp = str(ad / f'_upload_{role}.bin')
        file.save(tmp)
        dst = str(ad / f'{role}_ref.wav')
        with open(tmp, 'rb') as fin:
            with open(dst, 'wb') as fout:
                shutil.copyfileobj(fin, fout)
        os.unlink(tmp)
        dur = fdur(dst)
        for r in STATE['roles']:
            if r['role'] == role: r['audio_path'] = str(Path(dst).resolve()); r['duration'] = round(dur, 1); break
        return jsonify({'ok': True, 'role': role, 'duration': round(dur, 1)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/regenerate', methods=['POST'])
def a_regen():
    try:
        d = request.get_json()
        role = d.get('role')
        if not role: return jsonify({'error': 'missing role'}), 400
        desc = d.get('desc') or next((r['desc'] for r in STATE['roles'] if r['role'] == role), '')
        text = d.get('text') or next((r['text'] for r in STATE['roles'] if r['role'] == role), '')
        with STATE['task_lock']:
            tid = len(STATE['task_queue'])
            STATE['task_queue'].append({
                'id': tid, 'role': role, 'desc': desc, 'text': text,
                'params': d.get('params', {}), 'status': 'queued', 'error': None, 'duration': None,
            })
        return jsonify({'ok': True, 'task_id': tid})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/role', methods=['POST'])
def a_role():
    try:
        d = request.get_json()
        role = d.get('role')
        if not role: return jsonify({'error': 'missing role'}), 400
        for r in STATE['roles']:
            if r['role'] == role:
                if 'desc' in d: r['desc'] = d['desc']
                if 'text' in d: r['text'] = d['text']
                break
        save_vs()
        return jsonify({'ok': True})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/queue')
def a_queue():
    with STATE['task_lock']:
        return jsonify({'queue': list(STATE['task_queue']), 'current_index': STATE['task_index']})

@app.route('/api/done', methods=['POST'])
def a_done():
    print('Done - exiting')
    os._exit(0)

def worker():
    while STATE['running']:
        task = None
        with STATE['task_lock']:
            if STATE['task_index'] < len(STATE['task_queue']):
                task = STATE['task_queue'][STATE['task_index']]
                task['status'] = 'processing'
                STATE['task_index'] += 1
        if task is None:
            time.sleep(0.5)
            continue
        role, desc, text = task['role'], task['desc'], task['text']
        p = STATE['params'].copy()
        p.update(task.get('params', {}))
        print(f'[tuner] regen [{role}] desc={desc[:40]}')
        try:
            raw = call_vox(text=text, ci=desc, **p)
            if not os.path.exists(raw):
                raise RuntimeError(f'VoxCPM2 output missing: {raw}')
            ad = Path(STATE['target']) / 'tts_output' / 'auto_refs'
            ad.mkdir(parents=True, exist_ok=True)
            dst = str(ad / f'{role}_ref.wav')
            with open(raw, 'rb') as fin:
                with open(dst, 'wb') as fout:
                    shutil.copyfileobj(fin, fout)
            dur = fdur(dst)
            for r in STATE['roles']:
                if r['role'] == role:
                    r['audio_path'] = str(Path(dst).resolve())
                    r['duration'] = round(dur, 1)
                    break
            task['status'] = 'done'
            task['duration'] = round(dur, 1)
            print(f'  done ({dur:.1f}s)')
        except Exception as e:
            task['status'] = 'error'
            task['error'] = str(e)
            traceback.print_exc()
            print(f'  error: {e}')


def main():
    p = argparse.ArgumentParser(description='Voice Tuner')
    p.add_argument('--target', required=True)
    p.add_argument('--url', default='http://localhost:8808')
    p.add_argument('--port', type=int, default=DEFAULT_PORT)
    p.add_argument('--no-browser', action='store_true')
    args = p.parse_args()
    target = Path(args.target).resolve()
    STATE['target'] = target; STATE['vox_url'] = args.url
    print(f'Voice Tuner: target={target} url={args.url}')
    STATE['roles'] = load_roles(target)
    print(f'Loaded {len(STATE["roles"])} roles')
    for r in STATE['roles']: print(f'  [{r["role"]}] dur={r.get("duration")}')

    kill_port(args.port)

    threading.Thread(target=worker, daemon=True).start()

    if not args.no_browser:
        import webbrowser; webbrowser.open(f'http://localhost:{args.port}')
    print(f'http://localhost:{args.port}')
    try: app.run(threaded=True, host='0.0.0.0', port=args.port, debug=False, use_reloader=False)
    except KeyboardInterrupt: pass
    print('Stopped')

if __name__ == '__main__': 
    main()