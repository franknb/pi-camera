# pi-camera
Personalized deployment of SunFounder Pan-Tilt module/camera/CV application

# ssh to pi:

same network connection:
```bash
ssh frank@raspberrypi.local
```
general ip connection (yields to change)
```bash
ssh frank@192.168.68.123
```

password is same as this laptop

if this does not work, use 
```bash
hostname -I
```
on raspberry pi to get updated IP address

# run service
```python
cd pi-camera
python cam.py
```