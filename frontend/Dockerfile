# Build the React app, then serve the static files from nginx.
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY src ./src
# Where the browser reaches the API. Vite bakes it into the bundle.
ARG API_ORIGIN
ENV VITE_API_BASE_URL=${API_ORIGIN}
RUN npm run build

FROM nginx:1.27-alpine
# The official image runs envsubst over templates at start, so API_ORIGIN in
# the Content-Security-Policy is filled in from the container's environment.
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
