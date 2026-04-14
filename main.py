import os
import exifread
import folium
import urllib.parse

def dms_to_decimal(dms_list, ref):
    """将 EXIF 中的度分秒格式转换为 WGS84 十进制度"""
    degrees = float(dms_list[0].num) / float(dms_list[0].den)
    minutes = float(dms_list[1].num) / float(dms_list[1].den)
    seconds = float(dms_list[2].num) / float(dms_list[2].den)
    
    decimal = degrees + (minutes / 60.0) + (seconds / 3600.0)
    if ref in ['S', 'W']:
        decimal = -decimal
    return decimal

def get_encoded_url(cloud_base_url, relative_path):
    """
    将包含中文的本地相对路径转化为标准云端 URL
    """
    # 确保在不同系统下生成的路径逻辑一致
    normalized_path = relative_path.replace(os.sep, '/')
    
    # 执行 URL 编码
    encoded_path = urllib.parse.quote(normalized_path, safe='/')
    
    # 拼接基础 URL 和编码后的路径
    final_url = f"{cloud_base_url}/{encoded_path}"
    
    return final_url

def process_photos_and_generate_map(local_photo_dir, cloud_base_url):
    print(f"系统开始扫描数据源目录及其底层子架构: {local_photo_dir}")
    m = folium.Map(location=[35.0, 105.0], zoom_start=4, tiles="CartoDB positron")
    
    valid_count = 0
    # 采用 os.walk 执行目录树的自顶向下递归遍历
    for root, dirs, files in os.walk(local_photo_dir):
        for filename in files:
            if not filename.lower().endswith(('.jpg', '.jpeg')):
                continue
                
            filepath = os.path.join(root, filename)
            
            # 计算当前文件实体相对于根级输入目录的相对路径拓扑
            rel_path = os.path.relpath(filepath, local_photo_dir)
            
            with open(filepath, 'rb') as f:
                tags = exifread.process_file(f, details=False)
                
            if 'GPS GPSLatitude' in tags and 'GPS GPSLongitude' in tags:
                lat_dms = tags['GPS GPSLatitude'].values
                lat_ref = tags['GPS GPSLatitudeRef'].printable
                lon_dms = tags['GPS GPSLongitude'].values
                lon_ref = tags['GPS GPSLongitudeRef'].printable
                
                lat = dms_to_decimal(lat_dms, lat_ref)
                lon = dms_to_decimal(lon_dms, lon_ref)
                date_time = tags.get('EXIF DateTimeOriginal', '未知时间')
                
                # 使用get_encoded_url函数处理中文路径
                image_url = get_encoded_url(cloud_base_url, rel_path)
                
                popup_html = f"""
                <div style="width: 200px; font-family: sans-serif;">
                    <a href="{image_url}" target="_blank">
                        <img src="{image_url}" style="width: 100%; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">
                    </a>
                    <p style="margin-top: 8px; font-size: 12px; color: #555; text-align: center;">{date_time}</p>
                </div>
                """
                
                folium.Marker(
                    location=[lat, lon],
                    popup=folium.Popup(popup_html, max_width=250),
                    icon=folium.Icon(color="blue", icon="camera", prefix='fa')
                ).add_to(m)
                valid_count += 1
                print(f"已成功解析节点: {rel_path} -> 空间坐标: ({lat:.4f}, {lon:.4f})")
                
    m.save("index.html")
    print(f"\n批处理管线执行完毕。空间映射矩阵已注入 {valid_count} 个对象节点。输出持久化文件: index.html")

if __name__ == "__main__":
    TARGET_DIR = os.path.join(os.path.dirname(__file__), "..", "photos")
    CLOUD_URL = "https://travel-map-data-1422023265.cos.ap-shanghai.myqcloud.com"
    
    process_photos_and_generate_map(TARGET_DIR, CLOUD_URL)