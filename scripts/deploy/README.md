# Deployment Scripts

- `deploy-production.sh`: Backend·Frontend 이미지 빌드, 컨테이너 기동 및 HTTPS 검증
- `deploy-mqtt.sh`: MQTT Broker 인증서 동기화, 독립 배포 및 상태 검증
- `verify-mqtt.sh`: MQTTS 인증과 발행·구독 smoke test
- `renew-certificates.sh`: Let's Encrypt 인증서 갱신 및 Nginx·Mosquitto reload
- 자세한 운영 배포 절차: `DEPLOYMENT.md`
- MQTT 최초 설정 및 Jenkins 등록 절차: `MQTT_DEPLOYMENT.md`

비밀값은 스크립트에 작성하지 않고 EC2의
`/home/ubuntu/bomi/secrets/production.env`에서만 관리합니다.
MQTT 비밀값은 `/home/ubuntu/bomi/secrets/mqtt.env`와
`/home/ubuntu/bomi/secrets/mosquitto/passwords`에서 별도로 관리합니다.
