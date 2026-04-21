# Deploy

`hahoe-genesis` 서버에 상시 구동 배포.

## 전제

- 서버 접속 가능 (`ssh hahoe-genesis`)
- 서버에 Docker, Python 3.11+, git 설치
- GitHub 레포가 푸시되어 있음

## 주의

> Telegram은 **같은 봇 토큰을 두 곳에서 동시에 폴링할 수 없다.**
> 노트북에서 봇이 돌고 있다면 서버에 배포하기 전 반드시 중지해야 한다.

## 1. 노트북 측 정리

```bash
# 봇 프로세스 중지 (Ctrl+C)
docker compose down

# 로그아웃 (선택적, 봇의 세션을 완전히 끊는다)
curl "https://api.telegram.org/bot$BOT_TOKEN/logOut"
```

## 2. 서버에 클론

```bash
ssh hahoe-genesis
cd ~/projects
git clone https://github.com/hahnryu/cheroki.git
cd cheroki

# 환경변수
cp .env.example .env
$EDITOR .env   # 노트북과 동일한 값으로 채움

# 파이썬 환경
uv venv
source .venv/bin/activate
uv pip install -e .
```

## 3. Local Bot API 서버 (Docker)

```bash
docker compose up -d
docker compose logs -f telegram-bot-api
```

`Server is listening on port 8081`이 뜨면 OK. Ctrl+C로 로그 빠져나옴.

## 4. 봇 상시 구동 (systemd)

`/etc/systemd/system/cheroki.service`:

```ini
[Unit]
Description=Cheroki Telegram bot
After=docker.service network-online.target
Wants=docker.service network-online.target

[Service]
Type=simple
User=hahnryu
WorkingDirectory=/home/hahnryu/projects/cheroki
EnvironmentFile=/home/hahnryu/projects/cheroki/.env
ExecStart=/home/hahnryu/projects/cheroki/.venv/bin/python -m cheroki.interfaces.telegram
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now cheroki
sudo systemctl status cheroki
journalctl -u cheroki -f
```

## 5. 확인

Telegram에서 @cheroki_siltarebot에게 짧은 음성 하나 전송 → 응답 오면 성공.

## 6. 업데이트

```bash
ssh hahoe-genesis
cd ~/projects/cheroki
git pull
source .venv/bin/activate
uv pip install -e . --upgrade
sudo systemctl restart cheroki
```

스키마 변경이 있으면 `data/siltare.db` 백업 후 수동 마이그레이션.

## 7. 백업

`data/` 폴더 전체를 주기적으로 백업한다. 특히:
- `data/siltare.db` — 모든 메타데이터
- `data/uploads/` — 원본 오디오 (구술사는 디지털 문화재)
- `data/exports/` — 녹취 산출물

간단한 cron 예시:
```bash
# 매일 새벽 4시, 1주 보관
0 4 * * * tar czf /backup/cheroki-$(date +\%Y\%m\%d).tgz -C /home/hahnryu/projects/cheroki data && find /backup -name 'cheroki-*.tgz' -mtime +7 -delete
```

## 트러블슈팅

### 봇이 Conflict 에러
다른 곳(노트북 등)에서 같은 토큰으로 폴링 중. 해당 프로세스 찾아 종료 후 재시작.

### Docker 컨테이너가 재부팅 후 안 뜸
`restart: unless-stopped`가 설정되어 있지만, 서버 부팅 직후 docker.service가 늦게 뜨는 경우가 있다. systemd 서비스에 `After=docker.service` 추가되어 있는지 확인.

### 디스크 부족
원본 오디오가 쌓여 가득 찬다. `data/uploads/`의 오래된 파일을 압축/이관하거나 별도 볼륨에 마운트.
