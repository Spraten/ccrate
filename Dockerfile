FROM node:24-bookworm AS build
COPY --from=golang:1.26-bookworm /usr/local/go /usr/local/go
ENV PATH=/usr/local/go/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
WORKDIR /src
RUN apt-get update && apt-get install -y --no-install-recommends git python3 ca-certificates && rm -rf /var/lib/apt/lists/* \
    && npm install --global pnpm@10.28.0
COPY deploy/build-homebox-backend.py deploy/build-homebox-ui.py deploy/build-label-ui.py /src/deploy/
COPY deploy/homebox_patchset.py deploy/homebox-patchset.json /src/deploy/
COPY deploy/homebox-patches/ /src/deploy/homebox-patches/
COPY homebox-ui/overlay /src/homebox-ui/overlay
COPY homebox-ui/pnpm-lock.yaml homebox-ui/upstream-typecheck.json /src/homebox-ui/
COPY homebox-backend/ /src/homebox-backend/
COPY kiosk/branding/ /src/kiosk/branding/
COPY kiosk/member-avatar.js kiosk/label-editor.js /src/kiosk/
COPY label-ui/ /src/label-ui/
RUN mkdir -p /src/work/toolchains/pnpm/node_modules/.bin \
    && printf '/usr/local\n' > /src/work/toolchains/node-path.txt \
    && printf '/usr/local/go\n' > /src/work/toolchains/go-path.txt \
    && ln -s /usr/local/bin/pnpm /src/work/toolchains/pnpm/node_modules/.bin/pnpm \
    && git init /src/upstream/homebox \
    && git -C /src/upstream/homebox remote add origin https://github.com/sysadminsmedia/homebox.git \
    && git -C /src/upstream/homebox fetch --depth 1 origin e01dd737238a3fa7e1a6454b37de6c6fc88c86e4 \
    && git -C /src/upstream/homebox checkout --detach FETCH_HEAD
RUN python3 -c "import runpy; runpy.run_path('/src/deploy/build-homebox-ui.py')['prepare']()" \
    && pnpm --dir /src/work/homebox-ui-build install --frozen-lockfile \
    && python3 /src/deploy/build-homebox-ui.py --toolchain-root /src/work/toolchains --upstream-root /src \
    && mkdir -p /src/work/homebox-ui-current \
    && cp -a /src/work/homebox-ui-build/.output/public/. /src/work/homebox-ui-current/ \
    && python3 /src/deploy/build-label-ui.py --source-root /src --output work/label-ui-build --toolchain-root /src/work/toolchains \
    && python3 /src/deploy/build-homebox-backend.py

FROM python:3.13-slim-bookworm AS runtime
ENV PATH=/usr/local/bin:/usr/local/sbin:/usr/bin:/usr/sbin:/bin:/sbin \
    WORKSHOP_LOCAL_TEST=1 \
    WORKSHOP_ROOT=/data \
    WORKSHOP_CODE_ROOT=/app \
    HOMEBOX_UI_ROOT=/app/public \
    WORKSHOP_LABEL_ASSET_ROOT=/app/label-ui \
    WORKSHOP_NODE=/usr/bin/node \
    WORKSHOP_NATIVE_BASE=http://127.0.0.1:17747 \
    WORKSHOP_NATIVE_PORT=17747 \
    WORKSHOP_COMPANION_PORT=17749 \
    WORKSHOP_PORT=17745 \
    HOMEBOX_WEB_HOST=127.0.0.1 \
    HOMEBOX_WEB_PORT=17747 \
    PLAYWRIGHT_BROWSERS_PATH=/usr \
    PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install -y --no-install-recommends chromium fonts-dejavu-core libzbar0 nodejs ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir Pillow qrcode cryptography zxing-cpp playwright
RUN useradd --system --uid 10001 --create-home --home-dir /home/localtest localtest \
    && mkdir -p /app /data /app/native \
    && chown -R 10001:10001 /app /data /home/localtest
COPY --chown=10001:10001 ops/ /app/ops/
COPY --chown=10001:10001 kiosk/ /app/kiosk/
COPY --chown=10001:10001 desktop/ /app/desktop/
COPY --chown=10001:10001 deploy/kiosk-server.py deploy/workshop-gateway.py deploy/local-test.py /app/deploy/
COPY --from=build --chown=10001:10001 /src/work/homebox-backend-build/homebox /app/native/homebox
COPY --from=build --chown=10001:10001 /src/work/homebox-ui-build/.output/public /app/public
COPY --from=build --chown=10001:10001 /src/work/label-ui-build /app/label-ui
COPY --chown=10001:10001 label-ui/src/starter-documents.json /app/label-ui/src/starter-documents.json
USER 10001:10001
EXPOSE 17745 17749
CMD ["python3", "/app/deploy/local-test.py"]
