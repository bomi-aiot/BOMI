# Deployment Scripts

- `deploy-production.sh`: Backend·Frontend 이미지 빌드, 컨테이너 기동 및 HTTPS 검증
- `renew-certificates.sh`: Let's Encrypt 인증서 갱신 및 Nginx reload
- 자세한 운영 배포 절차: `DEPLOYMENT.md`

비밀값은 스크립트에 작성하지 않고 EC2의
`/home/ubuntu/bomi/secrets/production.env`에서만 관리합니다.
