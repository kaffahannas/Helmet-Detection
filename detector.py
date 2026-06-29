import os
import threading
from collections import deque
from datetime import datetime
import time

import cv2
from ultralytics import YOLO
from flask import Flask, Response, jsonify, stream_with_context

# ─── Flask App ────────────────────────────────────────────────────────────────
app = Flask(__name__)

# ─── Config ───────────────────────────────────────────────────────────────────
# Pilih model yang ingin digunakan (Hapus tanda pagar '#' pada model pilihan Anda):
MODEL_PATH    = r"models\best1080.pt"                 # YOLOv8 Medium (classes: hat, nohat, person, etc.)
# MODEL_PATH    = r"models\bestv8L.pt"                  # YOLOv8 Large (classes: hat, nohat, person, etc.)
# MODEL_PATH    = r"models\best_latest_safety_dataset.pt" # YOLOv8 OBB (Oriented Bounding Box)
# MODEL_PATH    = r"models\best_safety_helmet_lisa.pt"    # YOLOv8 LISA (classes: head, helmet, person, etc.)

OUTPUT_FOLDER = "bukti_pelanggaran"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# ─── RTSP transport — must be set before any VideoCapture is created ──────────
# Forces TCP (reliable, ordered) instead of UDP (faster but packet-loss causes lag)
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"

# ─── Camera Sources ───────────────────────────────────────────────────────────
# Add / remove entries to change the number of cameras.
# Supported: RTSP URL string, local file path string, or int (webcam index).
SOURCES = [
    "rtsp://admin:Admin@123@10.127.11.226",   # CAM 1
    "rtsp://admin:Admin@123@10.127.11.228",   # CAM 2
    "rtsp://admin:Admin@123@10.127.11.229",   # CAM 3
    # "test1.mp4",                             # local video (for testing)
    # 0,                                       # webcam
]
N_CAMS = len(SOURCES)

# One YOLO instance per camera so inference threads don't share state
print(f"Loading {N_CAMS} YOLO model instance(s) from {MODEL_PATH} …")
_models = [YOLO(MODEL_PATH) for _ in range(N_CAMS)]
_class_names = list(_models[0].names.values())
print(f"Models ready.  Classes: {_class_names}")
# Sanity-check expected classes are present
for _expected in ("person", "helmet", "no helmet"):
    if not any(_expected in n.lower() for n in _class_names):
        print(f"  WARNING: no class matching '{_expected}' found — check model")

# ─── Per-camera shared state ──────────────────────────────────────────────────
_frames      = [None] * N_CAMS          # annotated output frames
_frame_locks = [threading.Lock() for _ in range(N_CAMS)]

_raw_frames      = [None] * N_CAMS      # latest raw frames from grabber
_raw_frame_locks = [threading.Lock() for _ in range(N_CAMS)]

_stats_list = [
    {
        "cam_id":          i,
        "source":          str(SOURCES[i]),
        "violation_count": 0,
        "is_recording":    False,
        "last_violation":  None,
        "fps":             0,
    }
    for i in range(N_CAMS)
]
_stats_locks = [threading.Lock() for _ in range(N_CAMS)]
_cam_connected = [False] * N_CAMS

# ─── Detection helpers ────────────────────────────────────────────────────────
def _get_box(box):
    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
    return [float(x1), float(y1), float(x2), float(y2)]

def _center(b):
    return (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0

def _overlap(region, box):
    ix1 = max(region[0], box[0]); iy1 = max(region[1], box[1])
    ix2 = min(region[2], box[2]); iy2 = min(region[3], box[3])
    iw  = max(0.0, ix2 - ix1);    ih  = max(0.0, iy2 - iy1)
    ba  = max(0.0, (box[2] - box[0]) * (box[3] - box[1]))
    return (iw * ih / ba) if ba else 0.0

def _helmet_on_head(person, helmet):
    px1, py1, px2, py2 = person
    ph   = max(1.0, py2 - py1)
    head = [px1, max(0.0, py1 - ph * 0.10), px2, py1 + ph * 0.35]
    cx, cy = _center(helmet)
    return (px1 < cx < px2 and head[1] < cy < head[3]) or _overlap(head, helmet) >= 0.18


def _extract(results, cam_id):
    """Return (persons, helmets, no_helmets) for the detected boxes.
    Supports both standard object detection and Oriented Bounding Boxes (OBB).
    """
    persons, helmets, no_helmets = [], [], []
    model_instance = _models[cam_id]
    
    # Check if this is an OBB result
    is_obb = hasattr(results[0], 'obb') and results[0].obb is not None and len(results[0].obb) > 0
    
    if is_obb:
        obb = results[0].obb
        clss = obb.cls.cpu().numpy()
        confs = obb.conf.cpu().numpy()
        xyxyxyxy = obb.xyxyxyxy.cpu().numpy() # shape (N, 4, 2)
        
        for i in range(len(clss)):
            raw = model_instance.names[int(clss[i])]
            name = raw.lower().strip()
            conf = float(confs[i])
            
            # Convert oriented bounding box corners (4 points) to horizontal bounding box (xyxy)
            corners = xyxyxyxy[i]
            x1 = float(corners[:, 0].min())
            y1 = float(corners[:, 1].min())
            x2 = float(corners[:, 0].max())
            y2 = float(corners[:, 1].max())
            c = [x1, y1, x2, y2]
            
            if 'person' in name or 'worker' in name:
                if conf >= 0.50:
                    persons.append(c)
            elif name == 'head' or ('no' in name and ('helmet' in name or 'hard' in name or 'hat' in name)):
                if conf >= 0.65:
                    no_helmets.append(c)
            elif 'helmet' in name or 'hard' in name or 'hat' in name:
                if conf >= 0.40:
                    helmets.append(c)
    else:
        # Standard object detection
        if results[0].boxes is not None:
            for box in results[0].boxes:
                raw  = model_instance.names[int(box.cls[0].cpu().numpy())]
                name = raw.lower().strip()
                c    = _get_box(box)
                conf = float(box.conf[0].cpu().numpy())
                
                if 'person' in name or 'worker' in name:
                    if conf >= 0.50:
                        persons.append(c)
                elif name == 'head' or ('no' in name and ('helmet' in name or 'hard' in name or 'hat' in name)):
                    if conf >= 0.65:
                        no_helmets.append(c)
                elif 'helmet' in name or 'hard' in name or 'hat' in name:
                    if conf >= 0.40:
                        helmets.append(c)
                        
    return persons, helmets, no_helmets

# ─── Frame grabber (live sources only) ───────────────────────────────────────
def _frame_grabber(cam_id):
    """Continuously reconnects and grabs frames from RTSP/camera source,
    preventing freezes and buffer overflows.
    """
    global _cam_connected
    src = SOURCES[cam_id]
    tag = f"[CAM{cam_id + 1} Grabber]"
    
    while True:
        cap = (cv2.VideoCapture(src, cv2.CAP_DSHOW)
               if isinstance(src, int)
               else cv2.VideoCapture(src))
               
        if not cap.isOpened():
            print(f"{tag} ERROR: Cannot open {src!r}. Retrying in 5s...")
            _cam_connected[cam_id] = False
            cap.release()
            time.sleep(5)
            continue
            
        print(f"{tag} Connected to {src!r}")
        _cam_connected[cam_id] = True
        consecutive_failures = 0
        
        while cap.isOpened():
            ok, frame = cap.read()
            if ok:
                consecutive_failures = 0
                _cam_connected[cam_id] = True
                with _raw_frame_locks[cam_id]:
                    _raw_frames[cam_id] = frame
            else:
                consecutive_failures += 1
                if consecutive_failures >= 30:  # ~1 second of failure
                    print(f"{tag} Connection lost. Reconnecting...")
                    _cam_connected[cam_id] = False
                    break
                time.sleep(0.03)
                
        cap.release()
        _cam_connected[cam_id] = False
        time.sleep(2)

# ─── Detection thread (one per camera) ───────────────────────────────────────
def _run_detection(cam_id):
    src = SOURCES[cam_id]
    tag = f"[CAM{cam_id + 1}]"
    is_file = isinstance(src, str) and not src.startswith("rtsp")

    if is_file:
        cap = (cv2.VideoCapture(src, cv2.CAP_DSHOW)
               if isinstance(src, int)
               else cv2.VideoCapture(src))
        if not cap.isOpened():
            print(f"{tag} ERROR: Cannot open file {src!r}")
            return
        print(f"{tag} Opened file: {src!r}")
        fps     = int(cap.get(cv2.CAP_PROP_FPS)) or 30
        out_fps = max(fps, 10)
    else:
        # Start grabber thread to manage connection
        threading.Thread(
            target=_frame_grabber, args=(cam_id,), daemon=True
        ).start()
        print(f"{tag} Reconnecting grabber thread started")
        fps     = 15
        out_fps = 15

    frame_buf   = deque(maxlen=fps * 2)
    person_hist = deque(maxlen=5)
    helmet_hist = deque(maxlen=5)
    nh_hist     = deque(maxlen=5)
    miss_p = miss_h = miss_nh = 0

    is_rec  = False
    rec_end = 0.0
    writer  = None
    total_violations = 0

    detect_n = 5  # Skip frames to boost FPS (especially on CPU)
    count    = 0
    last_p, last_h, last_nh = [], [], []

    fps_t0 = time.time()
    fps_fc = 0
    violation_counter = 0

    while True:
        # ── Grab next frame ──────────────────────────────────────────────────
        if is_file:
            ok, frame = cap.read()
            if not ok:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                time.sleep(0.1)
                continue
            is_conn = True
        else:
            is_conn = _cam_connected[cam_id]
            with _raw_frame_locks[cam_id]:
                if _raw_frames[cam_id] is None:
                    time.sleep(0.05)
                    continue
                frame = _raw_frames[cam_id].copy()

        frame_buf.append(frame.copy())
        count  += 1
        fps_fc += 1

        # FPS counter
        elapsed = time.time() - fps_t0
        if elapsed >= 1.0:
            with _stats_locks[cam_id]:
                _stats_list[cam_id]["fps"] = round(fps_fc / elapsed, 1)
            fps_fc = 0
            fps_t0 = time.time()

        if is_conn:
            # YOLO inference every detect_n frames
            if count % detect_n == 0:
                res = _models[cam_id](frame, imgsz=1080, conf=0.35, verbose=False)
                persons, helmets, no_helmets = _extract(res, cam_id)

                # ── persons ──────────────────────────────────────────────────────
                if persons:
                    last_p = persons; person_hist.append(persons); miss_p = 0
                else:
                    miss_p += 1
                    if miss_p < 2 and person_hist:
                        persons = person_hist[-1]
                    else:
                        persons = []; last_p = []   # clear — nobody on screen

                # ── helmets ──────────────────────────────────────────────────────
                if helmets:
                    last_h = helmets; helmet_hist.append(helmets); miss_h = 0
                else:
                    miss_h += 1
                    if miss_h < 2 and helmet_hist:
                        helmets = helmet_hist[-1]
                    else:
                        helmets = []; last_h = []

                # ── no-helmet detections (direct model class) ─────────────────
                if no_helmets:
                    last_nh = no_helmets; nh_hist.append(no_helmets); miss_nh = 0
                else:
                    miss_nh += 1
                    if miss_nh < 2 and nh_hist:
                        no_helmets = nh_hist[-1]
                    else:
                        no_helmets = []; last_nh = []
            else:
                persons, helmets, no_helmets = last_p, last_h, last_nh

            persons    = persons    or []
            helmets    = helmets    or []
            no_helmets = no_helmets or []
            violation  = False

            # ── Draw person outlines (thin grey — context only) ──────────────
            for p in persons:
                cv2.rectangle(frame,
                              (int(p[0]), int(p[1])), (int(p[2]), int(p[3])),
                              (160, 160, 160), 1)

            # ── Draw helmet boxes GREEN ───────────────────────────────────────
            for h in helmets:
                cv2.rectangle(frame,
                              (int(h[0]), int(h[1])), (int(h[2]), int(h[3])),
                              (0, 200, 0), 2)
                cv2.putText(frame, "HELMET",
                            (int(h[0]), max(0, int(h[1]) - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 0), 2)

            frame_violation = False
            # ── Draw no-helmet boxes RED (helmet box nearby → skip) ──────────
            for nh in no_helmets:
                # If the head box is very small (person is far away), ignore it to prevent false alarms
                if (nh[3] - nh[1]) < 35:
                    continue

                # If any helmet detection overlaps this head, the helmet wins
                if any(_overlap(nh, h) >= 0.25 or _overlap(h, nh) >= 0.25
                       for h in helmets):
                    continue
                frame_violation = True
                cv2.rectangle(frame,
                              (int(nh[0]), int(nh[1])), (int(nh[2]), int(nh[3])),
                              (0, 0, 255), 2)
                cv2.putText(frame, "NO HELMET",
                            (int(nh[0]), max(0, int(nh[1]) - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)

            if frame_violation:
                violation_counter += 1
            else:
                violation_counter = 0

            if violation_counter >= 3:
                violation = True

            # Evidence recording
            if violation:
                if not is_rec:
                    is_rec = True
                    total_violations += 1
                    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
                    fname = os.path.join(OUTPUT_FOLDER, f"cam{cam_id + 1}_pelanggaran_{ts}.avi")
                    h, w  = frame.shape[:2]
                    writer = cv2.VideoWriter(
                        fname, cv2.VideoWriter_fourcc(*"XVID"), out_fps, (w, h))
                    for pf in frame_buf:
                        writer.write(pf)
                    with _stats_locks[cam_id]:
                        _stats_list[cam_id]["last_violation"]  = ts
                        _stats_list[cam_id]["violation_count"] = total_violations
                    print(f"{tag} Violation #{total_violations} — recording to {fname}")
                rec_end = time.monotonic() + 3

            if is_rec:
                cv2.putText(frame, "[REC]", (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
                writer.write(frame)
                if time.monotonic() >= rec_end and not violation:
                    is_rec = False
                    writer.release()
                    writer = None
        else:
            # Camera disconnected: draw dark overlay with warning message
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (frame.shape[1], frame.shape[0]), (0, 0, 0), -1)
            cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
            
            if int(time.time() * 2) % 2 == 0:
                text1 = "KONEKSI RTSP TERPUTUS"
                text2 = "Mencoba Menghubungkan Kembali..."
                
                t1_sz = cv2.getTextSize(text1, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)[0]
                t2_sz = cv2.getTextSize(text2, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0]
                
                x1 = (frame.shape[1] - t1_sz[0]) // 2
                y1 = frame.shape[0] // 2 - 10
                x2 = (frame.shape[1] - t2_sz[0]) // 2
                y2 = frame.shape[0] // 2 + 30
                
                cv2.putText(frame, text1, (x1, y1), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                cv2.putText(frame, text2, (x2, y2), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 1)

        # HUD: timestamp
        ts_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, ts_str, (10, frame.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (50, 50, 50), 1)

        with _stats_locks[cam_id]:
            _stats_list[cam_id]["is_recording"] = is_rec

        with _frame_locks[cam_id]:
            _frames[cam_id] = frame.copy()

    cap.release()
    if writer:
        writer.release()

# ─── MJPEG generator ─────────────────────────────────────────────────────────
def _generate(cam_id):
    while True:
        frame_data = None
        with _frame_locks[cam_id]:
            if _frames[cam_id] is not None:
                ok, buf = cv2.imencode(
                    '.jpg', _frames[cam_id], [cv2.IMWRITE_JPEG_QUALITY, 80])
                if ok:
                    frame_data = buf.tobytes()
        if frame_data is None:
            time.sleep(0.05)
            continue
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_data + b'\r\n')
        time.sleep(0.033)   # ~30 fps to browser

# ─── Flask routes ─────────────────────────────────────────────────────────────
@app.route('/video_feed/<int:cam_id>')
def video_feed(cam_id):
    if not 0 <= cam_id < N_CAMS:
        return "Camera not found", 404
    return Response(
        stream_with_context(_generate(cam_id)),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )

@app.route('/api/stats')
def api_stats_all():
    result = []
    for i in range(N_CAMS):
        with _stats_locks[i]:
            result.append(dict(_stats_list[i]))
    return jsonify(result)

@app.route('/api/stats/<int:cam_id>')
def api_stats_one(cam_id):
    if not 0 <= cam_id < N_CAMS:
        return jsonify({"error": "camera not found"}), 404
    with _stats_locks[cam_id]:
        return jsonify(dict(_stats_list[cam_id]))

@app.route('/api/violations')
def api_violations():
    files = []
    for f in sorted(os.listdir(OUTPUT_FOLDER), reverse=True):
        if f.endswith('.avi'):
            fp = os.path.join(OUTPUT_FOLDER, f)
            files.append({
                "name":    f,
                "size_mb": round(os.path.getsize(fp) / 1_048_576, 2),
                "created": datetime.fromtimestamp(
                    os.path.getctime(fp)
                ).strftime("%Y-%m-%d %H:%M:%S"),
            })
    return jsonify(files)

@app.route('/health')
def health():
    frame_ready = [_frames[i] is not None for i in range(N_CAMS)]
    return jsonify({
        "status":      "ok",
        "cameras":     N_CAMS,
        "frame_ready": frame_ready,
    })

# ─── Entry point ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    for i in range(N_CAMS):
        threading.Thread(
            target=_run_detection, args=(i,), daemon=True
        ).start()
    print(f"Detector running → http://localhost:5000  ({N_CAMS} cameras)")
    app.run(host='0.0.0.0', port=5000, threaded=True, use_reloader=False)
