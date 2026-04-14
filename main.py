import os
import exifread
import folium
import urllib.parse
from collections import defaultdict
from folium.plugins import MarkerCluster

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
    
    # 构建 JavaScript 回调函数，接管底层聚类图标的渲染管线
    cluster_icon_js = """
    function(cluster) {
        var count = cluster.getChildCount();
        // 利用 viewBox 锁定内部坐标系，仅将外层物理视口的长宽延伸至 200% (32x40)
        var svg = '<svg width="32" height="40" viewBox="0 0 16 20" xmlns="http://www.w3.org/2000/svg">' +
                  '<polygon points="2,11 14,11 8,20" fill="#3498db" />' +
                  '<circle cx="8" cy="8" r="5.8" fill="white" stroke="#3498db" stroke-width="1.6" />' +
                  '<text x="8" y="8.5" dy=".3em" font-size="9" font-family="sans-serif" font-weight="bold" fill="#3498db" text-anchor="middle">' + count + '</text>' +
                  '</svg>';
                  
        return L.divIcon({
            html: svg,
            className: 'custom-cluster-marker', 
            iconSize: L.point(32, 40), // 物理边界同步扩大一倍
            iconAnchor: L.point(16, 40) // 渲染锚点执行严格的几何补偿，确保坐标系统拓扑对齐
        });
    }
    """
    
    # 实例化空间聚类容器，同步注入自定义渲染函数与聚合物理距离阈值
    marker_cluster = MarkerCluster(
        maxClusterRadius=15,
        icon_create_function=cluster_icon_js
    ).add_to(m)
    
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
                image_url = get_encoded_url(cloud_base_url, rel_path)

                # 提取 EXIF 原始时间标签的内存对象
                raw_date_time = tags.get('EXIF DateTimeOriginal')
                if raw_date_time:
                    # 强制进行类型转换以获取 ASCII 文本
                    # 并利用限定执行次数的字符串替换，将标准格式重构为 YYYY-MM-DD HH:MM:SS
                    date_time = str(raw_date_time).replace(':', '-', 2)
                else:
                    date_time = '未知时间'
                
                # 语义提取：分离相对路径的目录结构并生成中文标签
                dir_parts = os.path.normpath(os.path.dirname(rel_path)).split(os.sep)
                # location_label = "，".join([p for p in dir_parts if p]) if dir_parts[0] != '.' else "未分类影像"
                location_label = dir_parts[-1] if dir_parts and dir_parts[0] != '.' else "未分类影像"
                
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
        
        # 引入响应式视口策略与媒体查询，重构弹窗渲染布局
        gallery_html = f"""
        <style>
            /* 默认状态下的高分辨率宽屏显示器渲染策略 */
            .leaflet-popup-content {{ margin: 24px !important; width: 960px !important; max-width: 90vw !important; }}
            .leaflet-popup-content p {{ margin: 0 !important; }}
            .gallery-container {{ width: 100%; font-family: sans-serif; }}
            .gallery-title {{ margin: 0 0 24px 0; color: #2c3e50; text-align: center; border-bottom: 3px solid #ecf0f1; padding-bottom: 18px; font-size: 30px; }}
            .gallery-count {{ font-size: 24px; color: #7f8c8d; }}
            .nav-button {{ background: #3498db; color: white; border: none; border-radius: 50%; width: 72px; height: 72px; cursor: pointer; font-size: 36px; display: flex; align-items: center; justify-content: center; box-shadow: 0 3px 12px rgba(0,0,0,0.2); flex-shrink: 0; padding: 0; outline: none; }}
            .nav-button-left {{ transform: translateY(-30px) translateX(8px); }}
            .nav-button-right {{ transform: translateY(-30px) translateX(-8px); }}
            .image-node {{ width: 100%; height: 600px; object-fit: cover; border-radius: 18px; box-shadow: 0 6px 18px rgba(0,0,0,0.15); cursor: pointer; }}
            .date-label {{ margin: 18px 0 0 0; font-size: 30px; color: #7f8c8d; }}
            
            /* 移动端视口自适应降级策略 (激活阈值: 768px) */
            @media (max-width: 768px) {{
                .leaflet-popup-content {{ margin: 12px !important; width: 320px !important; max-width: 85vw !important; }}
                .gallery-title {{ font-size: 20px; margin: 0 0 12px 0; padding-bottom: 10px; }}
                .gallery-count {{ font-size: 16px; }}
                .nav-button {{ width: 40px; height: 40px; font-size: 20px; }}
                .nav-button-left {{ transform: translateY(0); }}
                .nav-button-right {{ transform: translateY(0); }}
                .image-node {{ height: 250px; border-radius: 10px; }}
                .date-label {{ font-size: 16px; margin: 10px 0 0 0; }}
            }}
        </style>
        <div class="gallery-container">
        """
        
        gallery_html += f'<h4 class="gallery-title">{label} <span class="gallery-count">({len(photos)}张)</span></h4>'
        
        # 将左侧按钮赋予 nav-button-left 样式类
        gallery_html += f"""
        <div style="display: flex; align-items: center; gap: 4%;">
            <button onclick="var g = document.getElementById('gallery_{label}'); g.scrollBy({{left: -g.clientWidth, behavior: 'smooth'}})" class="nav-button nav-button-left">
                <span style="display: block; transform: translate(-2.5px, -3px);">&#10094;</span>
            </button>
            <div id="gallery_{label}" style="display: flex; overflow-x: auto; gap: 4%; scroll-snap-type: x mandatory; padding-bottom: 12px; flex: 1; scroll-behavior: smooth;">
        """
        
        for p in photos:
            img_url = p['url']
            img_date = p['date']
            gallery_html += f"""
            <div style="flex: 0 0 100%; scroll-snap-align: start; text-align: center;">
                <a href="#" onclick="if(confirm('确定要下载这张高清图片吗？')){{window.open('{img_url}', '_blank');}} return false;" style="text-decoration: none;">
                    <img src="{img_url}" class="image-node">
                </a>
                <p class="date-label">拍摄时间: {img_date}</p>
            </div>
            """
            
        gallery_html += '</div>'
        # 将右侧按钮赋予 nav-button-right 样式类
        gallery_html += f"""
            <button onclick="var g = document.getElementById('gallery_{label}'); g.scrollBy({{left: g.clientWidth, behavior: 'smooth'}})" class="nav-button nav-button-right">
                <span style="display: block; transform: translate(2.5px, -3px);">&#10095;</span>
            </button>
        </div></div>
        """
        
        # 1. 显式实例化 Tooltip 组件并注入 CSS 内联样式
        custom_tooltip = folium.Tooltip(
            label,
            style="font-size: 20px;"
        )
        
        # 构建放大一倍的矢量大头针
        # 物理视口扩张至 32px x 40px，利用 viewBox 锁定内部相对坐标系
        svg_icon = """
        <svg width="32" height="40" viewBox="0 0 16 20" xmlns="http://www.w3.org/2000/svg">
            <polygon points="2,11 14,11 8,20" fill="#3498db" />
            <circle cx="8" cy="8" r="5.15" fill="white" stroke="#3498db" stroke-width="3" />
        </svg>
        """

        custom_icon = folium.DivIcon(
            html=svg_icon,
            # 渲染锚点执行严格的几何补偿，与翻倍后的物理视口宽度中轴和高度底边绝对同步
            icon_anchor=(16, 40)
        )

        # 实例化地图组件，绑定聚合参数、自定义Tooltip和小巧的大头针图标
        folium.Marker(
            location=[center_lat, center_lon],
            tooltip=custom_tooltip,
            popup=folium.Popup(gallery_html, max_width=1000),
            icon=custom_icon
        ).add_to(marker_cluster)
        
        print(f"已构建聚类节点: {label} -> 包含 {len(photos)} 张影像，质心坐标: ({center_lat:.4f}, {center_lon:.4f})")
            
    m.save("index.html")
    print(f"\n底层引擎重构与渲染执行完毕。共抽取 {valid_count} 个物理节点，合成为 {len(cluster_data)} 个多维空间簇。最终输出: index.html")

if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 本地照片路径及腾讯云 COS 访问域名
    TARGET_DIR = os.path.join(current_dir, "..", "photos")
    CLOUD_URL = "https://travel-map-data-1422023265.cos.ap-shanghai.myqcloud.com"
    
    if os.path.exists(TARGET_DIR):
        process_photos_and_generate_map(TARGET_DIR, CLOUD_URL)
    else:
        print(f"环境自检异常：找不到目录 {TARGET_DIR}，请核实文件夹的物理位置。")