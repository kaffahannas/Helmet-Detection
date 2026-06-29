import os
from collections import deque
from datetime import datetime
import time

import cv2
import numpy as np
from ultralytics import YOLO

# Pilih model yang ingin digunakan (Hapus tanda pagar '#' pada model pilihan Anda):
# model_path = r"models\best1080.pt"                 # YOLOv8 Medium (classes: hat, nohat, person, etc.)
# model_path = r"models\bestv8L.pt"                  # YOLOv8 Large (classes: hat, nohat, person, etc.)
# model_path = r"models\best_latest_safety_dataset.pt" # YOLOv8 OBB (Oriented Bounding Box)
# model_path = r"models\best_safety_helmet_lisa.pt"    # YOLOv8 LISA (classes: head, helmet, person, etc.)
model_path = r"models\best.pt"

model = YOLO(model_path)
output_folder = "bukti_pelanggaran"
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# Pengaturan Video & Parameter Rekaman
#video = "test2.mp4"
#rtsp_url = "rtsp://admin:Admin@123@10.127.11.228"
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

fps = int(cap.get(cv2.CAP_PROP_FPS))
if fps == 0:
    fps = 15

output_fps = max(fps, 10)

detik_sebelum = 2
detik_sesudah = 3

buffer_frames = fps * detik_sebelum
post_record_frames = fps * detik_sesudah

frame_buffer = deque(maxlen=buffer_frames)

person_history = deque(maxlen=5)
helmet_history = deque(maxlen=5)
no_helmet_history = deque(maxlen=5)

missing_person_frames = 0
missing_helmet_frames = 0
missing_no_helmet_frames = 0

is_recording = False
record_end_time = 0.0
out = None

print("Sistem Aktif... Tekan 'q' untuk berhenti.")

detect_every_n = 5  # Increased from 2 to boost CPU FPS
frame_count = 0
last_persons = []
last_helmets = []
last_no_helmets = []


def get_box_coordinates(box):
    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
    return [float(x1), float(y1), float(x2), float(y2)]


def box_center(box):
    x1, y1, x2, y2 = box
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def overlap_ratio(region, box):
    x1, y1, x2, y2 = region
    bx1, by1, bx2, by2 = box
    inter_x1 = max(x1, bx1)
    inter_y1 = max(y1, by1)
    inter_x2 = min(x2, bx2)
    inter_y2 = min(y2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    intersection = inter_w * inter_h
    box_area = max(0.0, (bx2 - bx1) * (by2 - by1))
    if box_area == 0.0:
        return 0.0
    return intersection / box_area


def helmet_on_head(person_box, helmet_box):
    px1, py1, px2, py2 = person_box
    person_height = max(1.0, py2 - py1)
    
    # Toleransi area kepala: dari sedikit di atas kotak, sampai SETENGAH (50%) tinggi kotak
    # Ini mengatasi masalah kotak person yang tidak akurat (kebesaran)
    head_top = py1 - person_height * 0.10
    head_bottom = py1 + person_height * 0.35
    head_region = [px1, max(0.0, head_top), px2, head_bottom]

    center_x, center_y = box_center(helmet_box)
    center_inside_head = px1 < center_x < px2 and head_region[1] < center_y < head_bottom
    overlap_head = overlap_ratio(head_region, helmet_box)

    return center_inside_head or overlap_head >= 0.18


def extract_detections(results):
    """Extract persons, helmets, and no_helmets from YOLO results.
    Supports both standard object detection and Oriented Bounding Boxes (OBB).
    """
    persons, helmets, no_helmets = [], [], []
    
    # Check if this is an OBB result
    is_obb = hasattr(results[0], 'obb') and results[0].obb is not None and len(results[0].obb) > 0
    
    if is_obb:
        obb = results[0].obb
        clss = obb.cls.cpu().numpy()
        confs = obb.conf.cpu().numpy()
        xyxyxyxy = obb.xyxyxyxy.cpu().numpy() # shape (N, 4, 2)
        
        for i in range(len(clss)):
            raw = model.names[int(clss[i])]
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
                raw  = model.names[int(box.cls[0].cpu().numpy())]
                name = raw.lower().strip()
                c    = get_box_coordinates(box)
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


violation_counter = 0
while cap.isOpened():
    success, frame = cap.read()
    if not success:
        break

    frame_bersih = frame.copy()
    frame_buffer.append(frame_bersih)

    frame_count += 1
    if frame_count % detect_every_n == 0:
        results = model(frame, imgsz=640, conf=0.35, verbose=False)
        persons, helmets, no_helmets = extract_detections(results)

        if persons:
            last_persons = persons
            person_history.append(persons)
            missing_person_frames = 0
        else:
            missing_person_frames += 1
            if missing_person_frames < 3 and person_history:
                persons = person_history[-1]
            else:
                persons = []
                last_persons = []

        if helmets:
            last_helmets = helmets
            helmet_history.append(helmets)
            missing_helmet_frames = 0
        else:
            missing_helmet_frames += 1
            if missing_helmet_frames < 3 and helmet_history:
                helmets = helmet_history[-1]
            else:
                helmets = []
                last_helmets = []

        if no_helmets:
            last_no_helmets = no_helmets
            no_helmet_history.append(no_helmets)
            missing_no_helmet_frames = 0
        else:
            missing_no_helmet_frames += 1
            if missing_no_helmet_frames < 3 and no_helmet_history:
                no_helmets = no_helmet_history[-1]
            else:
                no_helmets = []
                last_no_helmets = []
    else:
        persons = last_persons
        helmets = last_helmets
        no_helmets = last_no_helmets

    persons = persons or []
    helmets = helmets or []
    no_helmets = no_helmets or []

    ada_pelanggaran = False
    frame_violation = False

    # Draw person outlines (thin grey)
    for px1, py1, px2, py2 in persons:
        cv2.rectangle(frame, (int(px1), int(py1)), (int(px2), int(py2)), (160, 160, 160), 1)

    # Draw helmet boxes GREEN
    for hx1, hy1, hx2, hy2 in helmets:
        cv2.rectangle(frame, (int(hx1), int(hy1)), (int(hx2), int(hy2)), (0, 200, 0), 2)
        cv2.putText(frame, "HELMET", (int(hx1), max(0, int(hy1) - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 0), 2)

    # Draw no-helmet boxes RED
    for nhx1, nhy1, nhx2, nhy2 in no_helmets:
        # Distance filter: ignore small heads
        if (nhy2 - nhy1) < 35:
            continue
            
        # Overlap filter: if head overlaps with a green helmet, it is not a violation
        is_covered = False
        for hx1, hy1, hx2, hy2 in helmets:
            if overlap_ratio([nhx1, nhy1, nhx2, nhy2], [hx1, hy1, hx2, hy2]) >= 0.25 or \
               overlap_ratio([hx1, hy1, hx2, hy2], [nhx1, nhy1, nhx2, nhy2]) >= 0.25:
                is_covered = True
                break
        
        if is_covered:
            continue

        frame_violation = True
        cv2.rectangle(frame, (int(nhx1), int(nhy1)), (int(nhx2), int(nhy2)), (0, 0, 255), 2)
        cv2.putText(frame, "NO HELMET", (int(nhx1), max(0, int(nhy1) - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)

    if frame_violation:
        violation_counter += 1
    else:
        violation_counter = 0

    if violation_counter >= 3:
        ada_pelanggaran = True

    if ada_pelanggaran:
            if not is_recording:
                is_recording = True
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                file_name = os.path.join(output_folder, f"pelanggaran_{timestamp}.avi")

                fourcc = cv2.VideoWriter_fourcc(*"XVID")
                h, w = frame.shape[:2]
                out = cv2.VideoWriter(file_name, fourcc, output_fps, (w, h))
                print(f"[{timestamp}] Pelanggaran terdeteksi! Menyimpan bukti...")

                for past_frame in frame_buffer:
                    out.write(past_frame)

            record_end_time = time.monotonic() + detik_sesudah
    if is_recording:
        cv2.putText(frame, "● REC", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 3)
        out.write(frame)

        if time.monotonic() >= record_end_time and not ada_pelanggaran:
            is_recording = False
            out.release()
            print("Rekaman bukti berhasil disimpan secara utuh.")

    cv2.imshow("Bintang Toedjoe - Advanced Video Evidence", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

if out:
    out.release()
cap.release()
cv2.destroyAllWindows()
