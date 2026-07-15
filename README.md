# Go2 Vision-Language-Action Pipeline
 
A closed-loop perception → reasoning → control pipeline running on a Unitree Go2 quadruped: the robot streams live camera video over Ethernet, detects objects with YOLOv8, and uses an LLM (cloud or local) to decide movement actions in real time to search for and approach a target object.
 
![demo placeholder](docs/demo.gif)
*(replace with your screen recording — camera feed + terminal detections + robot moving)*
 
## What this demonstrates
 
- Real-time video streaming from robot hardware over a custom transport (GStreamer/RTP over multicast UDP)
- Computer vision integration (YOLOv8 object detection) on a live robotic sensor feed
- LLM-based decision making in a robotics control loop, with both cloud (Claude API) and local (Ollama) backends
- ROS2 (Humble) as the middleware connecting perception, reasoning, and actuation
- End-to-end system design: every stage is a decoupled ROS2 node communicating over topics, so components can be swapped independently (e.g. any detector, any LLM, any robot with a `/cmd_vel` interface)
## Architecture
 
```
┌─────────────────┐     ┌──────────────────┐     ┌───────────────────┐     ┌──────────────────┐
│  Go2 Camera      │     │  Object Detection │     │   LLM Planner      │     │  Go2 Motion       │
│  (Ethernet/RTP)  │────▶│  (YOLOv8)          │────▶│  (Claude/Ollama)   │────▶│  (/cmd_vel)       │
│                  │     │                    │     │                    │     │                    │
│ go2_camera_      │     │ go2_target_        │     │ go2_llm_planner.py │     │ Go2 SDK sport      │
│ publisher.py     │     │ search.py          │     │ / go2_local_llm_   │     │ client (existing)  │
│                  │     │                    │     │ planner.py         │     │                    │
└─────────────────┘     └──────────────────┘     └───────────────────┘     └──────────────────┘
   /go2_camera/            /go2_camera/               /cmd_vel
   image_raw                target_status
```
 
Each stage is an independent ROS2 node. Data flows one-directional through topics — no stage needs to know how the others are implemented.
 
## Pipeline stages
 
| Stage | File | What it does |
|---|---|---|
| 1. Camera ingestion | `go2_camera_publisher.py` | Pulls the Go2's H264 multicast RTP stream (Ethernet mode) via GStreamer and republishes frames as a ROS2 `sensor_msgs/Image` topic |
| 2. Object detection & search | `go2_target_search.py` | Runs YOLOv8 on each frame, checks for a specified target class, reports its position (left/center/right) on a status topic, and publishes an annotated image with bounding boxes |
| 3. LLM planning (cloud) | `go2_llm_planner.py` | Sends detection status to Claude, receives a movement decision, publishes it as a `geometry_msgs/Twist` command |
| 3. LLM planning (local) | `go2_local_llm_planner.py` | Same as above but uses a locally-hosted Ollama model — no API key or cost, runs fully offline |
 
## Setup
 
### Hardware / connection
- Unitree Go2, connected via Ethernet cable
- Host machine on Ubuntu 22.04 (tested in a VMware VM, bridged/NAT networking to reach the robot's multicast stream)
- ROS2 Humble
### Dependencies
 
```bash
# ROS2 / GStreamer for camera ingestion
sudo apt install -y python3-gi python3-gi-cairo gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
  gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
  ros-humble-cv-bridge python3-opencv ros-humble-vision-msgs
 
# Object detection
pip install ultralytics
 
# LLM planner (choose one)
pip install anthropic        # for go2_llm_planner.py (cloud)
pip install requests         # for go2_local_llm_planner.py (local, uses Ollama)
```
 
For the local planner, install [Ollama](https://ollama.com) and pull a model:
```bash
ollama pull llama3:latest
```
 
### Network setup (Ethernet camera stream)
 
The Go2 streams video as multicast RTP on `230.1.1.1:1720` when connected via Ethernet. Route it on your interface:
```bash
sudo ip route add 230.1.1.1 dev <your-ethernet-interface>
```
 
## Running it
 
Requires 3 terminals, each running one stage of the pipeline:
 
```bash
# Terminal 1 — camera
source /opt/ros/humble/setup.bash
python3 src/go2_camera_publisher.py
 
# Terminal 2 — detection + search (pass any COCO class name)
source /opt/ros/humble/setup.bash
python3 src/go2_target_search.py bottle
 
# Terminal 3 — LLM planner (cloud or local)
source /opt/ros/humble/setup.bash
python3 src/go2_llm_planner.py          # cloud (needs ANTHROPIC_API_KEY)
# or
python3 src/go2_local_llm_planner.py    # local (needs Ollama running)
```
 
Watch the live annotated feed:
```bash
ros2 run rqt_image_view rqt_image_view /go2_camera/detections_image
```
 
## Results
 
- Robot reliably detects and localizes a target object (e.g. water bottle) in its camera frame
- LLM correctly maps detection position → turn direction in the majority of cycles
- Full loop latency (frame capture → detection → LLM decision → motion command): ~1.5-2s per cycle
*(Add specific numbers/observations once you've run more trials — e.g. success rate finding an object in an empty room, average time-to-find, comparison of cloud vs local LLM decision quality.)*
 
## Known limitations / future work
 
- LLM planner runs on a fixed interval rather than reacting instantly to new detections — could be event-driven
- No obstacle avoidance layer between the LLM's motion commands and the robot's built-in obstacle avoidance
- Single-target search only; no multi-object task planning yet
- No voice input — commands are hardcoded as a CLI argument rather than spoken
- Local LLM (llama3) is noticeably slower per decision than the cloud model; a smaller quantized model or event-based triggering would reduce latency
## Stack
 
`ROS2 Humble` · `GStreamer` · `OpenCV` · `YOLOv8 (Ultralytics)` · `Claude API` / `Ollama` · `Unitree Go2 SDK`
