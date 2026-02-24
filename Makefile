# Build directory
BUILD_DIR := ./editor/dist

ifeq ($(OS),Windows_NT)
	MKDIR = if not exist "$(BUILD_DIR)" mkdir "$(BUILD_DIR)"
	RM = del /Q
else
	MKDIR = mkdir -p $(BUILD_DIR)
	RM = rm -f
endif

PORT ?= 7421
API_PORT ?= 8000

.PHONY: help install dev build run clean server docker-build docker-up docker-upd docker-down docker-logs

## help: Display this help message
help:
	@echo Symbol Studio - Makefile commands:
	@echo   make install           - Install all dependencies (Python + Node.js)
	@echo   make dev               - Start Vite dev server (frontend)
	@echo   make build             - Build frontend for production
	@echo   make server            - Start Python server
	@echo   make run               - Start both server and dev server
	@echo   make clean             - Clean build artifacts
	@echo   make docker-build      - Build Docker images
	@echo   make docker-up         - Start Docker containers
	@echo   make docker-upd        - Start Docker containers (detached)
	@echo   make docker-down       - Stop Docker containers
	@echo   make docker-logs       - View Docker logs

## install: Install Python and Node.js dependencies
install:
	@echo Installing Python dependencies...
	uv sync
	@echo Installing Node.js dependencies...
	cd editor && npm install

## dev: Start Vite dev server
dev:
	@echo Starting Vite dev server...
	cd editor && npm run dev

## build: Build frontend for production
build:
	@echo Building frontend...
	cd editor && npm run build

## server: Start Python server
server:
	@echo Starting Python server...
	python symbol_studio.py

## run: Start both server and dev server
run: server dev

## clean: Clean build artifacts
clean:
	@echo Cleaning build artifacts...
	cd editor && $(RM) dist 2>NUL || true
	cd editor && $(RM) .vite 2>NUL || true

## docker-build: Build Docker images
docker-build:
	@echo Building Docker images...
	docker compose build

## docker-up: Start Docker containers
docker-up:
	@echo Starting Docker containers...
	docker compose up --build

## docker-upd: Start Docker containers (detached)
docker-upd:
	@echo Starting Docker containers (detached)...
	docker compose up --build -d

## docker-down: Stop Docker containers
docker-down:
	@echo Stopping Docker containers...
	docker compose down

## docker-logs: View Docker logs
docker-logs:
	docker compose logs -f
