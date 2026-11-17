resolver 127.0.0.11 valid=10s ipv6=off;

location / {
    set $agent_backend http://172.18.0.1:8000;
    proxy_pass $agent_backend;

    proxy_http_version 1.1;
    proxy_set_header Host $http_host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";

    proxy_buffering off;
    proxy_cache off;
    proxy_connect_timeout 5s;
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;
}