FROM openresty/openresty:alpine

RUN addgroup -S appgroup && adduser -S appuser -G appgroup

RUN mkdir -p /var/www/html \
    /var/run/openresty \
    /var/cache/nginx/client_temp \
    /usr/local/openresty/nginx/logs \
    && chown -R appuser:appgroup \
    /var/www/html \
    /var/run/openresty \
    /var/cache/nginx \
    /usr/local/openresty/nginx/logs

COPY nginx/default.conf /etc/nginx/conf.d/default.conf

USER appuser

EXPOSE 8080
