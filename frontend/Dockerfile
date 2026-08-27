# Frontend image: build with Node, serve static via nginx. One source tree
# builds every product's app; APP selects which (lead today, play later).
FROM node:20-alpine AS build
ARG APP=lead
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build:${APP}

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
