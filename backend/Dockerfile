FROM eclipse-temurin:17-jdk-jammy AS builder

WORKDIR /workspace

COPY gradlew settings.gradle build.gradle ./
COPY gradle ./gradle
RUN chmod +x gradlew && ./gradlew dependencies --no-daemon

COPY src ./src
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
