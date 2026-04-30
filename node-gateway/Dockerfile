FROM node:20-alpine

# Cài đặt công cụ build cần thiết (nếu có thư viện native)
RUN apk add --no-cache python3 make g++

WORKDIR /app

# Copy package files
COPY package*.json ./
RUN npm install

# Copy toàn bộ code
COPY . .

# Mở cổng 3000
EXPOSE 3000

CMD ["node", "src/app.js"]