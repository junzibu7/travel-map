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
        // 动态生成与独立标记拓扑一致的 SVG 矢量流，并利用 dy=".3em" 实现数字的绝对光学居中
        var svg = '<svg width="16" height="20" viewBox="0 0 16 20" xmlns="http://www.w3.org/2000/svg">' +
                  '<polygon points="2,11 14,11 8,20" fill="#3498db" />' +
                  '<circle cx="8" cy="8" r="5.8" fill="white" stroke="#3498db" stroke-width="1.4" />' +
                  '<text x="8" y="8.5" dy=".3em" font-size="8" font-family="sans-serif" font-weight="bold" fill="#3498db" text-anchor="middle">' + count + '</text>' +
                  '</svg>';
                  
        return L.divIcon({
            html: svg,
            className: 'custom-cluster-marker', // 注入自定义类名以屏蔽引擎默认的背景渲染
            iconSize: L.point(16, 20),
            iconAnchor: L.point(8, 20)
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
                date_time = tags.get('EXIF DateTimeOriginal', '未知时间')
                image_url = get_encoded_url(cloud_base_url, rel_path)
                
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
        
        # 1. 注入内联 CSS 覆盖 Leaflet 原生弹窗的厚重白边，并设定紧凑的容器基准
        gallery_html = f"""
        <style>
            .leaflet-popup-content {{ margin: 8px !important; width: 320px !important; }}
            .leaflet-popup-content p {{ margin: 0 !important; }}
        </style>
        <div style="width: 320px; font-family: sans-serif;">
        """
        
        # 收紧标题的上下留白与边框间距
        gallery_html += f'<h4 style="margin: 0 0 8px 0; color: #2c3e50; text-align: center; border-bottom: 1px solid #ecf0f1; padding-bottom: 6px; font-size: 10px;">{label} <span style="font-size: 8px; color: #7f8c8d;">({len(photos)}张)</span></h4>'
        
        # 2. 注入精准布局：应用 translateY(-10px) 对齐图片中线，运用子节点补偿消除箭头视觉偏移
        gallery_html += f"""
        <div style="display: flex; align-items: center; gap: 8px;">
            <button onclick="document.getElementById('gallery_{label}').scrollBy({{left: -320, behavior: 'smooth'}})" style="background: #3498db; color: white; border: none; border-radius: 50%; width: 24px; height: 24px; cursor: pointer; font-size: 12px; display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 4px rgba(0,0,0,0.2); flex-shrink: 0; padding: 0; transform: translateY(-10px); outline: none;">
                <span style="display: block; margin-top: -1.5px; margin-left: -1.5px;">&#10094;</span>
            </button>
            <div id="gallery_{label}" style="display: flex; overflow-x: auto; gap: 8px; scroll-snap-type: x mandatory; padding-bottom: 4px; flex: 1; scroll-behavior: smooth;">
        """
        
        # 动态注入簇内影像，收紧内部边距
        for p in photos:
            img_url = p['url']
            img_date = p['date']
            
            gallery_html += f"""
            <div style="flex: 0 0 100%; scroll-snap-align: start; text-align: center;">
                <a href="#" onclick="if(confirm('确定要下载这张高清图片吗？')){{window.open('{img_url}', '_blank');}} return false;" style="text-decoration: none;" title="点击查看高清原图">
                    <img src="{img_url}" style="width: 100%; height: 200px; object-fit: cover; border-radius: 6px; box-shadow: 0 2px 6px rgba(0,0,0,0.15); cursor: pointer;">
                </a>
                <p style="margin: 6px 0 0 0; font-size: 10px; color: #7f8c8d;">拍摄时间: {img_date}</p>
            </div>
            """
            
        gallery_html += '</div>'
        # 右侧按钮同步执行几何补偿与光学居中调整
        gallery_html += f"""
            <button onclick="document.getElementById('gallery_{label}').scrollBy({{left: 320, behavior: 'smooth'}})" style="background: #3498db; color: white; border: none; border-radius: 50%; width: 24px; height: 24px; cursor: pointer; font-size: 12px; display: flex; align-items: center; justify-content: center; box-shadow: 0 1px 4px rgba(0,0,0,0.2); flex-shrink: 0; padding: 0; transform: translateY(-10px); outline: none;">
                <span style="display: block; margin-top: -1.5px; margin-left: 1.5px;">&#10095;</span>
            </button>
        </div></div>
        """
        
        # 1. 显式实例化 Tooltip 组件并注入 CSS 内联样式
        custom_tooltip = folium.Tooltip(
            label,
            style="font-size: 10px;"
        )
        
        # 构建矢量大头针
        # 设计规范：16px x 32px 尺寸，蓝白配色
        svg_icon = """
        <svg width="16" height="20" viewBox="0 0 16 20" xmlns="http://www.w3.org/2000/svg">
            <polygon points="2,11 14,11 8,20" fill="#3498db" />
            <circle cx="8" cy="8" r="5.15" fill="white" stroke="#3498db" stroke-width="3" />
        </svg>
        """

        custom_icon = folium.DivIcon(
            html=svg_icon,
            # 渲染锚点必须与 SVG 画布的新高度保持绝对同步
            icon_anchor=(8, 20)
        )

        # 实例化地图组件，绑定聚合参数、自定义Tooltip和小巧的大头针图标
        folium.Marker(
            location=[center_lat, center_lon],
            tooltip=custom_tooltip,
            popup=folium.Popup(gallery_html, max_width=450),
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