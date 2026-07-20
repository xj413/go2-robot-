#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import Twist
from anthropic import Anthropic

SYSTEM_PROMPT = """You control a quadruped robot searching for a target object using its camera.
You will be given the latest detection status. Reply with EXACTLY ONE of these words and nothing else:
TURN_LEFT   - target is on the left side of frame
TURN_RIGHT  - target is on the right side of frame
FORWARD     - target is centered, walk toward it
STOP        - target is centered and confidently found, stop
SEARCH      - target not visible, rotate slowly to scan the room
"""

TURN_SPEED = 0.4
FORWARD_SPEED = 0.25
SEARCH_SPEED = 0.2
LLM_CALL_INTERVAL_SEC = 1.5  # don't call the API every frame


class Go2LLMPlanner(Node):
    def __init__(self):
        super().__init__('go2_llm_planner')
        self.client = Anthropic()  # reads ANTHROPIC_API_KEY from env
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.sub = self.create_subscription(
            String, '/go2_camera/target_status', self.on_status, 10
        )
        self.latest_status = None
        self.timer = self.create_timer(LLM_CALL_INTERVAL_SEC, self.plan_step)
        self.get_logger().info('LLM planner started, waiting for detection status...')

    def on_status(self, msg: String):
        self.latest_status = msg.data

    def plan_step(self):
        if self.latest_status is None:
            return

        status = self.latest_status
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=10,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"Detection status: {status}\nAction:"}]
            )
            action = response.content[0].text.strip().upper()
        except Exception as e:
            self.get_logger().error(f'LLM call failed: {e}')
            return

        self.get_logger().info(f'status="{status}" -> action={action}')
        self.execute(action)

    def execute(self, action: str):
        twist = Twist()
        if action == 'TURN_LEFT':
            twist.angular.z = TURN_SPEED
        elif action == 'TURN_RIGHT':
            twist.angular.z = -TURN_SPEED
        elif action == 'FORWARD':
            twist.linear.x = FORWARD_SPEED
        elif action == 'SEARCH':
            twist.angular.z = SEARCH_SPEED
        elif action == 'STOP':
            pass  # zero twist = stop
        else:
            self.get_logger().warn(f'Unrecognized action "{action}", stopping')
        self.cmd_pub.publish(twist)


def main():
    rclpy.init()
    node = Go2LLMPlanner()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.cmd_pub.publish(Twist())  # send stop command on exit
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
