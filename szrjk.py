'''
Author: Guan zhenguo
Date: 2026-07-27 10:22:11
LastEditors: Guan Zhenguo
LastEditTime: 2026-07-27 10:22:18
Description: xxx
FilePath: \工艺\szrjk.py
'''
import subprocess
import os

def get_cpu_info_native():
    print("="*50)
    print("🖥️  CPU 信息 (原生方式)")
    print("="*50)
    
    try:
        with open('/proc/cpuinfo', 'r') as f:
            lines = f.readlines()
            
        model_name = "Unknown"
        cpu_cores = 0
        
        for line in lines:
            if line.startswith("model name"):
                model_name = line.split(':')[1].strip()
            if line.startswith("processor"):
                cpu_cores += 1
                
        print(f"CPU 型号: {model_name}")
        print(f"逻辑核心数: {cpu_cores}")
    except Exception as e:
        print(f"读取 CPU 信息失败: {e}")
        
    # 使用 uptime 命令获取负载
    try:
        result = subprocess.run(['uptime'], capture_output=True, text=True, check=True)
        print(f"系统负载: {result.stdout.strip().split('load average:')[1].strip()}")
    except Exception:
        pass
    print("\n")

def get_process_info_native():
    print("="*50)
    print("⚙️  进程信息 (调用系统 ps 命令)")
    print("="*50)
    
    try:
        # 使用 ps 命令，按 CPU 降序排列，输出前 15 行
        # aux: 显示所有用户进程, --sort=-%cpu: 按CPU降序
        cmd = ['ps', 'aux', '--sort=-%cpu']
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        lines = result.stdout.strip().split('\n')
        
        # 打印表头
        print(lines[0])
        print("-" * 110)
        
        # 打印前 15 个进程 (跳过表头)
        for line in lines[1:16]:
            print(line)
            
    except subprocess.CalledProcessError as e:
        print(f"执行 ps 命令失败: {e}")
    except FileNotFoundError:
        print("找不到 ps 命令，请确认系统环境。")

if __name__ == "__main__":
    get_cpu_info_native()
    get_process_info_native()