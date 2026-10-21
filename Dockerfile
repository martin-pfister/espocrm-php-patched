# syntax=docker/dockerfile:1
# Adapted from EspoCRM's 9.3.8 Apache Dockerfile, 2026-10-21.
# Upstream: espocrm/espocrm-docker@a6d862f43d825289dd219088d5187931ca7493d6
# Changes: patched PHP base, pinned PECL versions, source metadata, and a
# commit-pinned upstream stage instead of locally copied startup scripts.

ARG PHP_BASE_IMAGE=php:8.4.27-apache-trixie

FROM scratch AS upstream
ADD https://github.com/espocrm/espocrm-docker.git#a6d862f43d825289dd219088d5187931ca7493d6 /upstream/

FROM ${PHP_BASE_IMAGE}

LABEL org.opencontainers.image.source="https://github.com/martin-pfister/espocrm-php-patched" \
      org.opencontainers.image.description="Unofficial EspoCRM 9.3.8 rebuild with patched PHP; not an EspoCRM application upgrade." \
      org.opencontainers.image.licenses="AGPL-3.0-only"

# Persistent dependencies, as in the historical EspoCRM recipe.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends unzip libldap-common; \
    rm -rf /var/lib/apt/lists/*

# Rebuild EspoCRM's extensions against the patched PHP runtime.
# Explicit PECL versions avoid silently selecting newer releases on rebuild.
RUN set -eux; \
    aptMarkList="$(apt-mark showmanual)"; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        libpq-dev \
        libpng-dev \
        libjpeg-dev \
        libwebp-dev \
        libfreetype6-dev \
        libzip-dev \
        libxml2-dev \
        libldap2-dev \
        libzmq5-dev \
        zlib1g-dev; \
    cd /usr; \
    curl -fSL https://github.com/zeromq/php-zmq/archive/616b6c64ffd3866ed038615494306dd464ab53fc.tar.gz -o php-zmq.tar.gz; \
    tar -zxf php-zmq.tar.gz; \
    cd php-zmq-616b6c64ffd3866ed038615494306dd464ab53fc; \
    phpize; \
    ./configure; \
    make -j"$(nproc)"; \
    make install; \
    cd /usr; \
    rm -rf php-zmq*; \
    pecl install ev-1.2.3 redis-6.3.0; \
    docker-php-ext-configure ldap \
        --with-libdir="lib/$(dpkg-architecture --query DEB_BUILD_MULTIARCH)"; \
    docker-php-ext-configure gd \
        --with-freetype \
        --with-jpeg=/usr \
        --with-webp; \
    docker-php-ext-install -j"$(nproc)" \
        gd pdo_pgsql pdo_mysql zip ldap exif pcntl posix bcmath; \
    docker-php-ext-enable zmq ev redis; \
    rm -rf /tmp/pear; \
    apt-mark auto '.*' > /dev/null; \
    apt-mark manual $aptMarkList; \
    ldd "$(php -r 'echo ini_get("extension_dir");')"/*.so \
        | awk '/=>/ { so = $(NF-1); if (index(so, "/usr/local/") == 1) { next }; gsub("^/(usr/)?", "", so); printf "*%s\n", so }' \
        | sort -u \
        | xargs -r dpkg-query -S \
        | cut -d: -f1 \
        | sort -u \
        | xargs -rt apt-mark manual; \
    apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false; \
    rm -rf /var/lib/apt/lists/*

# Preserve the 9.3.8 image's PHP configuration.
RUN { \
    echo 'expose_php = Off'; \
    echo 'error_reporting = E_ALL & ~E_NOTICE & ~E_DEPRECATED'; \
    echo 'display_errors = Off'; \
    echo 'display_startup_errors = Off'; \
    echo 'log_errors = On'; \
    echo 'memory_limit=256M'; \
    echo 'max_execution_time=180'; \
    echo 'max_input_time=180'; \
    echo 'post_max_size=50M'; \
    echo 'upload_max_filesize=50M'; \
    echo 'date.timezone=UTC'; \
} > "${PHP_INI_DIR}/conf.d/espocrm.ini"

RUN a2enmod rewrite

# Application version and checksum are fixed, not build arguments.
ENV ESPOCRM_VERSION=9.3.8
ENV ESPOCRM_SHA256=e02583050c5f5a7e98cd12f9431870fc606581a62c10c5e4ef6dc091e882c18d

LABEL org.opencontainers.image.version="${ESPOCRM_VERSION}-php${PHP_VERSION}"

WORKDIR /var/www/html

RUN set -eux; \
    curl -fSL https://www.espocrm.com/downloads/EspoCRM-9.3.8.zip -o EspoCRM.zip; \
    echo "${ESPOCRM_SHA256} *EspoCRM.zip" | sha256sum -c -; \
    unzip -q EspoCRM.zip -d /usr/src; \
    mv "/usr/src/EspoCRM-${ESPOCRM_VERSION}" /usr/src/espocrm; \
    rm EspoCRM.zip

# Use the generated scripts, which already include entrypoint-utils.sh.
# The repository-root scripts are not the complete generated build context.
COPY --from=upstream --chmod=755 /upstream/latest/apache/docker-*.sh /usr/local/bin/
COPY --from=upstream /upstream/LICENSE /usr/local/share/espocrm-build/LICENSE
COPY --from=upstream /upstream/latest/apache/Dockerfile /usr/local/share/espocrm-build/upstream.Dockerfile

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["apache2-foreground"]
