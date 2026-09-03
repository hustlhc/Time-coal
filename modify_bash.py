import sys
import re

def modify_bash_param(file_path, param_name, new_value):
    """
    修改指定bash脚本中的参数值，如 seq_len、down_sampling_layers、moving_avg等。
    示例调用：
        python modify_bash_param.py scripts/long_term_forecast/autocoal/CCI4500.sh seq_len 64
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        pattern = re.compile(rf"^{param_name}=")
        found = False
        new_lines = []

        for line in lines:
            if pattern.match(line.strip()):
                # 修改对应参数
                new_line = f"{param_name}={new_value}\n"
                new_lines.append(new_line)
                found = True
            else:
                new_lines.append(line)

        if not found:
            print(f"⚠️ 参数 {param_name} 未在 {file_path} 中找到，未修改。")
        else:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            print(f"✅ 已修改 {file_path} 中的参数 {param_name}={new_value}")

    except FileNotFoundError:
        print(f"❌ 文件 {file_path} 未找到！")
    except Exception as e:
        print(f"❌ 出错：{e}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("用法: python modify_bash_param.py <bash_file_path> <param_name> <new_value>")
        sys.exit(1)

    file_path = sys.argv[1]
    param_name = sys.argv[2]
    new_value = sys.argv[3]

    modify_bash_param(file_path, param_name, new_value)