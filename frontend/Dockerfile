FROM node:20-alpine AS build
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY . .
RUN pnpm build
FROM node:20-alpine
WORKDIR /app
COPY --from=build /app ./
EXPOSE 3000
CMD ["node","node_modules/next/dist/bin/next","start"]
