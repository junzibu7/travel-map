import os
import exifread
import folium
import urllib.parse
from collections import defaultdict

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
    """将包含中文的本地相对路径转化为标准云端 URL"""
    normalized_path = relative_path.replace(os.sep, '/')
    encoded_path = urllib.parse.quote(normalized_path, safe='/')
    final_url = f"{cloud_base_url}/{encoded_path}"
    return final_url

def process_photos_and_generate_map(local_photo_dir, cloud_base_url):
    print(f"系统开始扫描数据源目录及其底层子架构: {local_photo_dir}")
    m = folium.Map(location=[26.0, 100.0], zoom_start=5, tiles="CartoDB positron")
    
    # 构建空间簇字典，键为提取的地理标签，值为影像节点列表
    cluster_data = defaultdict(list)
    valid_count = 0
    
    for root, dirs, files in os.walk(local_photo_dir):
        for filename in files:
            if not filename.lower().endswith(('.jpg', '.jpeg')):
                continue
                
            filepath = os.path.join(root, filename)
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
                image_url = get_encoded_url(cloud_base_url, rel_path)
                
                # 语义提取：分离相对路径的目录结构并生成中文标签
                dir_parts = os.path.normpath(os.path.dirname(rel_path)).split(os.sep)
                location_label = "，".join([p for p in dir_parts if p]) if dir_parts[0] else "未分类影像"
                
                cluster_data[location_label].append({
                    'lat': lat,
                    'lon': lon,
                    'url': image_url,
                    'date': date_time
                })
                valid_count += 1
                
    # 遍历空间簇执行聚合渲染与视图合成
    for label, photos in cluster_data.items():
        # 求解当前地理区域的空间质心
        center_lat = sum(p['lat'] for p in photos) / len(photos)
        center_lon = sum(p['lon'] for p in photos) / len(photos)

        # 构建基于 Flexbox 属性的横向滑动前端容器
        gallery_html = f'<div style="width: 400px; font-family: sans-serif;">'
        gallery_html += f'<h4 style="margin: 0 0 15px 0; color: #2c3e50; text-align: center; border-bottom: 2px solid #ecf0f1; padding-bottom: 12px; font-size: 12px;">{label} <span style="font-size: 10px; color: #7f8c8d;">({len(photos)}张)</span></h4>'
         
        # 添加左右翻页按钮和图片容器
        gallery_html += f'''
        <div style="display: flex; align-items: center; gap: 10px;">
            <button onclick="document.getElementById('gallery_{label}').scrollBy({{left: -400, behavior: 'smooth'}})" style="background: #3498db; color: white; border: none; border-radius: 50%; width: 40px; height: 40px; cursor: pointer; font-size: 20px; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 8px rgba(0,0,0,0.2); flex-shrink: 0;">&#10094;</button>
            <div id="gallery_{label}" style="display: flex; overflow-x: auto; gap: 15px; scroll-snap-type: x mandatory; padding-bottom: 10px; flex: 1; scroll-behavior: smooth;">
        '''
        
        # 动态注入簇内所有的独立影像流
        for p in photos:
            gallery_html += f'''
            <div style="flex: 0 0 100%; scroll-snap-align: start; text-align: center;">
                <a href="#" onclick="if(confirm('确定要下载这张图片吗？')){{window.open('{p['url']}', '_blank');}} return false;" style="text-decoration: none;">
                    <img src="{p['url']}" style="width: 100%; height: 250px; object-fit: cover; border-radius: 10px; box-shadow: 0 6px 12px rgba(0,0,0,0.15); cursor: pointer;">
                </a>
                <p style="margin: 8px 0 0 0; font-size: 14px; color: #7f8c8d;">拍摄时间: {p['date']}</p>
            </div>
            '''
            
        gallery_html += '</div>'
        gallery_html += f'<button onclick="document.getElementById(\'gallery_{label}\').scrollBy({{left: 400, behavior: \'smooth\'}})" style="background: #3498db; color: white; border: none; border-radius: 50%; width: 40px; height: 40px; cursor: pointer; font-size: 20px; display: flex; align-items: center; justify-content: center; box-shadow: 0 2px 8px rgba(0,0,0,0.2); flex-shrink: 0;">&#10095;</button>'
        gallery_html += '</div></div>'

        # 通过显式实例化 Tooltip 组件并注入 CSS 内联样式，将地图悬停标签的字号从标准值收敛至 8px
        custom_tooltip = folium.Tooltip(
            label,
            style="font-size: 8px; padding: 2px 4px; border-radius: 3px; background-color: rgba(255, 255, 255, 0.95); box-shadow: 0 1px 3px rgba(0,0,0,0.2);"
        )
        
        # 实例化地图组件，绑定聚合参数
        folium.Marker(
            location=[center_lat, center_lon],
            tooltip=custom_tooltip,
            popup=folium.Popup(gallery_html, max_width=450),
            icon=folium.Icon(color="darkblue", icon="images", prefix='fa')
        ).add_to(m)
        
        print(f"已构建聚类节点: {label} -> 包含 {len(photos)} 张影像，质心坐标: ({center_lat:.4f}, {center_lon:.4f})")
            
    m.save("index.html")
    print(f"\n底层引擎重构与渲染执行完毕。共抽取 {valid_count} 个物理节点，合成为 {len(cluster_data)} 个多维空间簇。最终输出: index.html")

if __name__ == "__main__":
    TARGET_DIR = os.path.join(os.path.dirname(__file__), "..", "photos")
    CLOUD_URL = "https://travel-map-data-1422023265.cos.ap-shanghai.myqcloud.com"
    
    process_photos_and_generate_map(TARGET_DIR, CLOUD_URL)