FROM php:8.2-fpm-alpine

WORKDIR /var/www/html

COPY ../app /var/www/html
COPY php/security.ini /usr/local/etc/php/conf.d/security.ini

RUN addgroup -S appgroup && adduser -S appuser -G appgroup

USER appuser

EXPOSE 9000
