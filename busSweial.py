#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
总线舵机控制脚本 - 通过串口控制总线舵机
命令格式: "<id>,<pulse_us>[,<time_ms>]" 例如: "0,1640,1000"
总线帧格式: ASCII "#<iii>P<pppp>T<tttt>!" 例如: "#000P1640T1000!"
"""

import serial
import time
import sys

# 串口配置
BUS_PORT = 'COM11'  # 根据实际情况修改串口号（Windows: COM3, Linux: /dev/ttyUSB0）
BUS_BAUD = 115200  # 舵机总线波特率
PULSE_MIN_US = 500  # 脉宽最小值（微秒）
PULSE_MAX_US = 2500  # 脉宽最大值（微秒）

# 全局默认时间（毫秒）
default_time_ms = 1000


class BusServoController:
    """总线舵机控制器类"""
    
    def __init__(self, port=BUS_PORT, baudrate=BUS_BAUD):
        """初始化串口连接"""
        try:
            self.serial = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
            print(f"串口已打开: {port} @ {baudrate} baud")
            time.sleep(0.1)  # 等待串口稳定
        except serial.SerialException as e:
            print(f"无法打开串口 {port}: {e}")
            sys.exit(1)
    
    def send_servo_move(self, servo_id, pulse_us, time_ms):
        """
        发送舵机移动命令
        :param servo_id: 舵机ID (0-999)
        :param pulse_us: 脉宽（微秒，500-2500）
        :param time_ms: 移动时间（毫秒）
        :return: 发送的帧字符串
        """
        # 限制参数范围
        pulse_us = max(PULSE_MIN_US, min(PULSE_MAX_US, pulse_us))
        time_ms = max(1, time_ms)  # 避免0时间移动
        servo_id = min(999, servo_id)  # 协议要求3位数
        
        # 构建帧: #<iii>P<pppp>T<tttt>!
        # ID: 3位, PulseUs: 4位, TimeMs: 4位（左侧补零）
        frame = f"#{servo_id:03d}P{pulse_us:04d}T{time_ms:04d}!"
        
        # 发送到串口
        self.serial.write(frame.encode('ascii'))
        return frame
    
    def send_passthrough(self, command):
        """
        发送透传命令（C#...!格式）
        :param command: 以C#开头、!结尾的完整命令
        :return: 从舵机接收的响应
        """
        if not command.upper().startswith('C#') or not command.endswith('!'):
            return "Invalid C# command (must start with C# and end with !)"
        
        # 提取#...!部分发送给舵机
        payload = command[1:]  # 去掉开头的'C'
        self.serial.write(payload.encode('ascii'))
        
        # 等待并读取响应
        time.sleep(0.05)
        response = ""
        while self.serial.in_waiting > 0:
            response += self.serial.read(self.serial.in_waiting).decode('ascii', errors='ignore')
        
        return f"C# sent -> {payload}" + (f"\nResponse: {response}" if response else "")
    
    def parse_segment(self, segment):
        """
        解析命令段 "id,pulse[,time]"
        :param segment: 命令段字符串
        :return: (id, pulse, time) 元组，失败返回 None
        """
        parts = segment.split(',')
        if len(parts) < 2:
            return None
        
        try:
            servo_id = int(parts[0])
            pulse = int(parts[1])
            time_ms = int(parts[2]) if len(parts) > 2 else default_time_ms
            
            if servo_id < 0 or servo_id > 999 or pulse <= 0 or time_ms <= 0:
                return None
            
            return (servo_id, pulse, time_ms)
        except ValueError:
            return None
    
    def process_command(self, line):
        """
        处理输入命令行
        :param line: 命令字符串
        """
        global default_time_ms
        
        line = line.strip()
        if not line:
            return
        
        # 处理透传命令 C#...!
        if line.upper().startswith('C#'):
            result = self.send_passthrough(line)
            print(result)
            return
        
        # 处理设置默认时间命令 ct<value>
        if line.startswith('ct'):
            try:
                new_time = int(line[2:])
                if new_time > 0:
                    default_time_ms = new_time
                    print(f"Default time set to: {default_time_ms} ms")
                else:
                    print("Invalid time value for ct command.")
            except ValueError:
                print("Invalid time value for ct command.")
            return
        
        # 处理舵机控制命令（支持用;分隔多个命令）
        segments = line.split(';')
        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue
            
            result = self.parse_segment(segment)
            if result:
                servo_id, pulse, time_ms = result
                frame = self.send_servo_move(servo_id, pulse, time_ms)
                print(f"Sent -> {frame}")
            else:
                print(f"Skip invalid segment: {segment}")
    
    def close(self):
        """关闭串口连接"""
        if self.serial and self.serial.is_open:
            self.serial.close()
            print("串口已关闭")


def main():
    """主函数 - 交互式命令行界面"""
    print("=" * 50)
    print("总线舵机控制器")
    print("=" * 50)
    print("命令格式:")
    print("  舵机移动: <id>,<pulse_us>[,<time_ms>]")
    print("  示例: 0,1640,1000  (舵机0移动到1640us，时间1000ms)")
    print("  多命令: 0,1500;1,2000  (用分号分隔)")
    print("  设置默认时间: ct<value>  (例如: ct500)")
    print("  透传命令: C#...!  (例如: C#000PRAD1500!)")
    print("  退出: quit 或 exit")
    print("=" * 50)
    
    # 创建控制器
    controller = BusServoController()
    
    try:
        print("\nReady: 请输入命令")
        while True:
            try:
                # 读取用户输入
                line = input("> ").strip()
                
                # 检查退出命令
                if line.lower() in ['quit', 'exit', 'q']:
                    print("退出中...")
                    break
                
                # 处理命令
                controller.process_command(line)
                
            except KeyboardInterrupt:
                print("\n中断，退出中...")
                break
    
    finally:
        controller.close()


if __name__ == '__main__':
    main()
