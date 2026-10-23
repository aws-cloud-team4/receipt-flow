# Static build served by nginx. /api, /chat, /preprocess are routed by the ALB ingress, not nginx.
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_COGNITO_CLIENT_ID
ARG VITE_REGION=ap-northeast-2
# "dev" only for the local container check (deploy/local); the cluster image uses Cognito.
ARG VITE_AUTH_MODE=cognito
ENV VITE_AUTH_MODE=$VITE_AUTH_MODE VITE_COGNITO_CLIENT_ID=$VITE_COGNITO_CLIENT_ID VITE_REGION=$VITE_REGION
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
