FROM php:8.2-fpm-alpine

WORKDIR /var/www/html

COPY ../app /var/www/html

RUN addgroup -S appgroup && adduser -S appuser -G appgroup

USER appuser

EXPOSE 9000
