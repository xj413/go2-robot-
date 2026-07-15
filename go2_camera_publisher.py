#!/usr/bin/env python3
import threading

import numpy as np
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from sensor_msgs.msg import Image

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib  # noqa: E402

# ---- EDIT THIS to match your ethernet interface name (from `ip addr`) ----
IFACE = "enx207bd51ad5fd"
# ---------------------------------------------------------------------------

PIPELINE = (
    f"udpsrc address=230.1.1.1 port=1720 multicast-iface={IFACE} "
    "! queue "
    "! application/x-rtp,media=video,encoding-name=H264 "
    "! rtph264depay ! h264parse ! avdec_h264 ! videoconvert "
    "! video/x-raw,format=BGR "
    "! appsink name=sink emit-signals=true sync=false max-buffers=1 drop=true"
)


class Go2CameraPublisher(Node):
    def __init__(self):
        super().__init__('go2_camera_publisher')
        self.pub = self.create_publisher(Image, '/go2_camera/image_raw', 10)
        self.bridge = CvBridge()

        Gst.init(None)
        self.pipeline = Gst.parse_launch(PIPELINE)
        self.sink = self.pipeline.get_by_name('sink')
        self.sink.connect('new-sample', self.on_new_sample)

        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            self.get_logger().error('Failed to start GStreamer pipeline')

        self.loop = GLib.MainLoop()
        self.glib_thread = threading.Thread(target=self.loop.run, daemon=True)
        self.glib_thread.start()

        self.get_logger().info(
            f'Go2 camera publisher started on iface="{IFACE}", '
            f'publishing to /go2_camera/image_raw'
        )

    def on_new_sample(self, sink):
        sample = sink.emit('pull-sample')
        if sample is None:
            return Gst.FlowReturn.ERROR

        buf = sample.get_buffer()
        caps = sample.get_caps()
        structure = caps.get_structure(0)
        width = structure.get_value('width')
        height = structure.get_value('height')

        success, mapinfo = buf.map(Gst.MapFlags.READ)
        if success:
            try:
                frame = np.ndarray(
                    (height, width, 3), buffer=mapinfo.data, dtype=np.uint8
                )
                msg = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')
                msg.header.stamp = self.get_clock().now().to_msg()
                msg.header.frame_id = 'go2_camera'
                self.pub.publish(msg)
            finally:
                buf.unmap(mapinfo)

        return Gst.FlowReturn.OK

    def destroy_node(self):
        self.pipeline.set_state(Gst.State.NULL)
        self.loop.quit()
        super().destroy_node()


def main():
    rclpy.init()
    node = Go2CameraPublisher()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
