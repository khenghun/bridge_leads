# kk_relay: a static two-file page (index.html + kkrelay.js), no build step.
# nginx serves the folder; TLS and the hostname live in the shared edge stack.
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html kkrelay.js /usr/share/nginx/html/
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
