FROM golang:1.22-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY *.go ./
RUN go build -o execution .

FROM alpine:3.19
RUN apk add --no-cache ca-certificates
COPY --from=builder /app/execution /execution
ENTRYPOINT ["/execution"]
