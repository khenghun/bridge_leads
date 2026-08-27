# Frontend image: build with Node, serve static via nginx. One source tree
# builds every product's app; APP selects which (lead, play).
FROM node:20-alpine AS build
ARG APP=lead
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build:${APP}

FROM nginx:alpine
# ARG does not cross stage boundaries — re-declare it to pick the vhost whose
# proxy target and timeouts match this product.
ARG APP=lead
COPY nginx.${APP}.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
