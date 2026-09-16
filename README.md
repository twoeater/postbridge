# Postbridge

Markdown 문서를 SQLite에 저장하고 Flask로 렌더링하는 경량 블로그입니다.

웹 애플리케이션은 게시 데이터를 읽기 전용으로 사용하며, 글 작성/수정은 서버 측 CLI, ntfy 트리거 또는 선택적인 MCP publisher를 통해 수행합니다. 사이트 이름, 공개 URL, 데이터 경로, ntfy 및 MCP 설정은 모두 환경변수로 구성할 수 있습니다.

## 주요 기능

- Markdown 게시 및 HTML 렌더링
- SQLite 기반 게시글 저장
- 태그, 검색, Atom feed, sitemap
- canonical URL, 페이지별 meta description, `BlogPosting` JSON-LD
- CLI 기반 publish/update/delete
- ntfy 메시지 및 Markdown 첨부를 이용한 자동 게시
- OAuth 2.1 + PKCE 기반 원격 MCP 게시 도구
- 단일 `.env` 파일을 통한 블로그/ntfy/MCP 설정

## 구성

```text
app/                    Flask 웹 애플리케이션
bin/blogctl              관리 CLI launcher
bin/blogctl.py           게시/삭제 구현
bin/publish-stdin        stdin 게시 helper
bin/ntfy-publisher       ntfy publisher launcher
bin/ntfy-publisher.py    ntfy polling/publishing 구현
bin/configure-ntfy-token ntfy 인증 설정 helper
mcp/                     MCP publisher
posts/                   Markdown 원본 기본 경로
data/                    SQLite DB 기본 경로
state/                   런타임 상태 기본 경로
.env.example             통합 환경설정 예제
```

실제 데이터 디렉터리는 `BLOG_DB`, `BLOG_POSTS_DIR`, `BLOG_STATE_DIR`로 변경할 수 있으므로 저장소 내부에 둘 필요는 없습니다.

## 환경 설정

모든 컴포넌트는 하나의 환경파일을 공유하도록 구성할 수 있습니다. 예제 파일을 복사한 뒤 배포 환경에 맞게 수정합니다.

```bash
cp .env.example /etc/postbridge/.env
chmod 600 /etc/postbridge/.env
```

중요한 기본 설정은 다음과 같습니다.

```ini
BLOG_SITE_NAME="Postbridge"
BLOG_SITE_URL=https://blog.example.com
BLOG_TIMEZONE=UTC
BLOG_LANGUAGE=en

BLOG_ROOT=/opt/postbridge
BLOG_DB=/var/lib/postbridge/blog.db
BLOG_POSTS_DIR=/var/lib/postbridge/posts
BLOG_STATE_DIR=/var/lib/postbridge/state
```

`BLOG_SITE_URL`은 게시 완료 URL, canonical URL, sitemap 및 robots 정보의 기준 주소로 사용됩니다. 실제 사이트 도메인을 소스 코드에 하드코딩할 필요가 없습니다.

전체 변수와 예시는 [`.env.example`](.env.example)을 참고하세요.

## Python 환경

예시:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

CLI launcher는 기본적으로 `${BLOG_ROOT}/.venv/bin/python`을 사용하며, 필요하면 `BLOG_PYTHON`으로 변경할 수 있습니다.

## 게시

파일 게시:

```bash
bin/blogctl publish --file /path/to/post.md
```

stdin 게시:

```bash
cat <<'EOF' | bin/publish-stdin
---
title: "Example post"
summary: "Short summary"
tags: [linux, networking]
---

## Section

Markdown body.
EOF
```

직접 제목을 지정할 수도 있습니다.

```bash
printf '%s\n' '## Hello' | \
  bin/blogctl publish --stdin --title 'Hello world' --slug hello-world
```

게시 완료 URL은 `${BLOG_SITE_URL}/post/<slug>` 형식으로 출력됩니다.

## 관리 명령

```bash
bin/blogctl list
bin/blogctl publish --file FILE
bin/blogctl publish --stdin [OPTIONS]
bin/blogctl delete SLUG
```

동일한 `slug`로 다시 게시하면 기존 글의 제목/본문/요약/태그를 갱신하고 최초 게시 시각은 유지합니다.

## 웹 애플리케이션

Flask 앱은 SQLite를 읽기 전용으로 열어 공개 페이지를 렌더링합니다.

Gunicorn 실행 예시:

```bash
set -a
. /etc/postbridge/.env
set +a

.venv/bin/gunicorn \
  --workers 2 \
  --bind 127.0.0.1:8765 \
  app:app
```

일반적인 배포에서는 nginx 또는 다른 reverse proxy가 TLS를 종료하고 `127.0.0.1:8765`로 전달하도록 구성할 수 있습니다.

## systemd와 통합 `.env`

웹, MCP, ntfy 서비스를 systemd로 실행할 경우 세 서비스가 동일한 환경 파일을 읽도록 구성할 수 있습니다.

```ini
EnvironmentFile=/etc/postbridge/.env
```

예를 들면 다음과 같이 역할을 분리할 수 있습니다.

```text
postbridge.service
postbridge-mcp.service
postbridge-ntfy.service
        │
        └── /etc/postbridge/.env
```

서비스 이름과 설치 위치는 배포 환경에 맞게 정하면 됩니다. 소스 코드에서 특정 systemd 서비스명을 요구하지 않습니다.

## ntfy publisher

ntfy publisher는 `NTFY_BASE_URL`의 `NTFY_TOPIC`을 polling하여 새 메시지를 게시글로 변환합니다.

필수 설정:

```ini
NTFY_BASE_URL=https://ntfy.example.com
NTFY_TOPIC=blog-publish
NTFY_TOKEN=
```

`NTFY_TOKEN`은 ntfy 웹 UI에서 **Account → Access tokens**로 이동한 뒤 새 access token을 생성해서 사용합니다. 생성된 token 값을 통합 `.env`의 `NTFY_TOKEN`에 넣습니다.

동작 방식:

- ntfy `Title` → 게시글 제목
- message body → Markdown 본문
- `.md` 또는 `.markdown` 첨부 → Markdown 본문으로 읽음
- body와 첨부가 모두 있으면 두 내용을 이어서 게시
- 제목과 동일한 첫 번째 `# H1`은 자동 제거
- 마지막 처리 message ID를 `NTFY_STATE_FILE`에 저장
- 최초 실행 시 기존 캐시 메시지를 모두 재게시하지 않도록 현재 시점을 cursor로 사용
- 첨부 URL은 설정한 ntfy 호스트의 HTTPS `/file/` URL만 허용

관련 설정:

```ini
NTFY_POLL_INTERVAL=5
NTFY_STATE_FILE=/var/lib/postbridge/ntfy-last-id
NTFY_MAX_ATTACHMENT_BYTES=5242880
NTFY_USER_AGENT=postbridge-ntfy-publisher/2.0
NTFY_SERVICE_NAME=postbridge-ntfy.service
```

`bin/configure-ntfy-token`은 통합 `.env`의 다른 설정은 보존하면서 `NTFY_BASE_URL`, `NTFY_TOPIC`, `NTFY_TOKEN`만 갱신합니다.

```bash
sudo bin/configure-ntfy-token /etc/postbridge/.env
```

## MCP publisher

`mcp/`에는 원격 MCP 클라이언트가 블로그 글을 게시할 수 있도록 하는 별도 publisher가 포함되어 있습니다.

MCP 공개 URL과 표시 이름 역시 설정값입니다.

```ini
MCP_PUBLIC_URL=https://blog.example.com
MCP_ALLOWED_HOSTS=blog.example.com
MCP_SERVER_NAME=postbridge-mcp
MCP_DISPLAY_NAME="Postbridge Publisher"
MCP_OAUTH_APPROVAL_KEY=
```

`MCP_OAUTH_APPROVAL_KEY`는 MCP OAuth 승인 화면에서 사용하는 서버 측 approval key입니다. 최소 32자 이상이어야 하며, OpenSSL로 충분히 긴 무작위 값을 만들 수 있습니다.

```bash
openssl rand -hex 32
```

예를 들어 생성된 값을 통합 `.env`에 다음과 같이 설정합니다.

```ini
MCP_OAUTH_APPROVAL_KEY=<openssl에서 생성한 값>
```

이 값은 OAuth access token 자체가 아니라 **OAuth 연결을 승인할 때 사용하는 비밀키**이며 Git에 커밋하면 안 됩니다. 실제 access/refresh token은 OAuth 흐름에서 발급됩니다.

기본 endpoint는 `${MCP_PUBLIC_URL}/mcp`이며 제공 도구는 `publish_blog` 하나입니다.

```text
publish_blog(title, markdown, slug?, date?, tags?, summary?)
```

MCP 서버는 shell/file/delete/general HTTP 도구를 제공하지 않으며, 설정된 `BLOGCTL_PATH`를 이용해 게시 작업만 수행합니다.

OAuth 및 상세 MCP 설정은 [`mcp/README.md`](mcp/README.md)를 참고하세요.

## 데이터 및 백업

기본적으로 다음 영역을 분리해서 관리하는 것을 권장합니다.

```text
application   BLOG_ROOT
SQLite        BLOG_DB
Markdown      BLOG_POSTS_DIR
runtime state BLOG_STATE_DIR
```

`BLOG_DB`, Markdown 원본 및 OAuth/ntfy 상태 파일은 애플리케이션 소스와 별도로 백업할 수 있습니다.

## 보안 메모

- 실제 `.env`에는 ntfy token과 MCP OAuth approval key가 포함될 수 있으므로 저장소에 커밋하지 마세요.
- `.env` 파일은 root 또는 서비스 사용자만 읽을 수 있도록 제한하는 것을 권장합니다.
- 웹 앱은 공개 HTTP 요청을 통해 글을 수정하지 않습니다.
- MCP를 인터넷에 노출할 경우 TLS reverse proxy, Host 검증, rate limit과 systemd sandboxing을 함께 사용하는 것을 권장합니다.

## 설정 예제

프로젝트에 포함된 `.env.example`은 특정 도메인이나 설치 위치에 종속되지 않는 예제입니다. 새 인스턴스를 구성할 때 이 파일을 기준으로 사이트 이름과 URL, 경로, ntfy 및 MCP 값을 설정하면 됩니다.
