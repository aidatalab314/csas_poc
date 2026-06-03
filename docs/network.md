# 實驗室網路架構

## 拓樸

```
MacBook (140.124.42.77)
    │
    │  靜態路由：192.168.6.0/24 → 192.168.0.87
    ▼
Ubuntu Server
    ├── 192.168.0.87  (內網，Mac 可直連)
    └── 192.168.6.87  (Camera 子網路，iptables NAT 轉發)
                │
                ├── Camera A (KMRT-1)  192.168.6.90  ✅
                └── Camera B (KMRT-2)  192.168.6.91  ✅
```

## RTSP 位址

| Camera | ID | RTSP URL | 編碼 |
|--------|----|----------|------|
| KMRT-1 | `camera_a` | `rtsp://root:root@192.168.6.90/cam1/h264` | H.265 |
| KMRT-2 | `camera_b` | `rtsp://root:root@192.168.6.91/cam1/h264` | H.265 |

> URL 路徑含 `h264` 為 AXIS 攝影機慣例命名，實際串流為 **H.265（HEVC）**。GStreamer pipeline 已對應使用 `rtph265depay`。

## Mac 開發環境設定（一次性）

### 新增靜態路由

```bash
# 暫時生效（重開機後消失）
sudo route add -net 192.168.6.0/24 192.168.0.87

# 永久生效
sudo networksetup -setadditionalroutes "Ethernet" 192.168.6.0 255.255.255.0 192.168.0.87
```

> 介面名稱（`Ethernet`）可用 `networksetup -listallnetworkservices` 確認。

### 連線確認

```bash
python3 -c "import cv2; cap = cv2.VideoCapture('rtsp://root:root@192.168.6.90/cam1/h264'); print('camera_a:', cap.isOpened()); cap.release()"
python3 -c "import cv2; cap = cv2.VideoCapture('rtsp://root:root@192.168.6.91/cam1/h264'); print('camera_b:', cap.isOpened()); cap.release()"
```

## Ubuntu 端設定（一次性）

### 開啟 IP 轉發與 NAT

```bash
# IP 轉發
sudo sysctl -w net.ipv4.ip_forward=1

# NAT Masquerade（Camera 子網路回程）
sudo iptables -t nat -A POSTROUTING -o eno1 -j MASQUERADE

# 允許 FORWARD（Docker 環境下需明確允許）
sudo iptables -I FORWARD -d 192.168.6.0/24 -j ACCEPT
sudo iptables -I FORWARD -s 192.168.6.0/24 -j ACCEPT
```

> Ubuntu 重開機後 iptables 規則會消失，需重新執行或設定 `iptables-persistent`。
