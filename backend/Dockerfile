FROM eclipse-temurin:17-jdk-jammy AS builder

WORKDIR /workspace

# 빌드 컨텍스트가 레포 루트이므로 경로에 backend/ 접두가 붙는다.
COPY backend/gradlew backend/settings.gradle backend/build.gradle ./
COPY backend/gradle ./gradle
RUN chmod +x gradlew && ./gradlew dependencies --no-daemon

COPY backend/src ./src
# 온보딩 질문셋 등 build.gradle 이 ${rootDir}/../docs 에서 읽는 문서 리소스.
# rootDir=/workspace 이므로 /workspace/../docs = /docs 위치에 놓는다.
COPY docs /docs
RUN ./gradlew bootJar --no-daemon \
    && find build/libs -maxdepth 1 -type f -name '*.jar' ! -name '*-plain.jar' \
       -exec cp '{}' build/libs/app.jar \;

FROM eclipse-temurin:17-jre-jammy

RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 bomi \
    && useradd --uid 10001 --gid bomi --no-create-home --shell /usr/sbin/nologin bomi

WORKDIR /app
COPY --from=builder --chown=bomi:bomi /workspace/build/libs/app.jar /app/app.jar

USER bomi
EXPOSE 8080

ENTRYPOINT ["java", "-jar", "/app/app.jar"]
