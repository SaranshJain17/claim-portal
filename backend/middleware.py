from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
import time
import logging
from typing import Callable
import asyncio
from collections import defaultdict, deque
from datetime import datetime, timedelta
import hashlib
import json

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    """Rate limiting middleware to prevent API abuse"""
    
    def __init__(self, calls: int = 100, period: int = 3600):
        """
        Args:
            calls: Number of calls allowed
            period: Time period in seconds
        """
        self.calls = calls
        self.period = period
        self.clients = defaultdict(deque)

    def __call__(self, request: Request, call_next: Callable):
        return self.process_request(request, call_next)

    async def process_request(self, request: Request, call_next: Callable):
        # Get client IP
        client_ip = self._get_client_ip(request)
        
        # Check rate limit
        if not self._is_allowed(client_ip):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later."
            )
        
        # Process request
        response = await call_next(request)
        return response

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request"""
        # Check for forwarded IP first (common in production deployments)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        # Check for real IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Fall back to client host
        return request.client.host if request.client else "unknown"

    def _is_allowed(self, client_ip: str) -> bool:
        """Check if client is within rate limit"""
        now = time.time()
        window_start = now - self.period
        
        # Clean old entries
        client_calls = self.clients[client_ip]
        while client_calls and client_calls[0] < window_start:
            client_calls.popleft()
        
        # Check if under limit
        if len(client_calls) >= self.calls:
            return False
        
        # Add current request
        client_calls.append(now)
        return True


class SecurityHeadersMiddleware:
    """Add security headers to all responses"""
    
    def __init__(self):
        self.security_headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';"
        }

    def __call__(self, request: Request, call_next: Callable):
        return self.process_request(request, call_next)

    async def process_request(self, request: Request, call_next: Callable):
        response = await call_next(request)
        
        # Add security headers
        for header, value in self.security_headers.items():
            response.headers[header] = value
        
        return response


class RequestValidationMiddleware:
    """Validate incoming requests for security"""
    
    def __init__(self):
        self.max_content_length = 50 * 1024 * 1024  # 50MB
        self.blocked_patterns = [
            r'<script',
            r'javascript:',
            r'eval\(',
            r'union.*select',
            r'drop.*table'
        ]

    def __call__(self, request: Request, call_next: Callable):
        return self.process_request(request, call_next)

    async def process_request(self, request: Request, call_next: Callable):
        # Check content length
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_content_length:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Request too large"
            )
        
        # Check for suspicious patterns in query parameters
        query_string = str(request.url.query).lower()
        for pattern in self.blocked_patterns:
            if pattern in query_string:
                logger.warning(f"Blocked suspicious request from {request.client.host}: {pattern}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid request"
                )
        
        response = await call_next(request)
        return response


class PerformanceMonitoringMiddleware:
    """Monitor API performance and log slow requests"""
    
    def __init__(self, slow_threshold: float = 2.0):
        """
        Args:
            slow_threshold: Time in seconds to consider a request slow
        """
        self.slow_threshold = slow_threshold
        self.request_stats = defaultdict(list)

    def __call__(self, request: Request, call_next: Callable):
        return self.process_request(request, call_next)

    async def process_request(self, request: Request, call_next: Callable):
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            # Calculate processing time
            processing_time = time.time() - start_time
            
            # Log slow requests
            if processing_time > self.slow_threshold:
                logger.warning(
                    f"Slow request: {request.method} {request.url.path} "
                    f"took {processing_time:.2f}s"
                )
            
            # Store stats for monitoring
            endpoint = f"{request.method} {request.url.path}"
            self.request_stats[endpoint].append(processing_time)
            
            # Keep only last 100 requests per endpoint
            if len(self.request_stats[endpoint]) > 100:
                self.request_stats[endpoint] = self.request_stats[endpoint][-100:]
            
            # Add performance header
            response.headers["X-Response-Time"] = f"{processing_time:.3f}s"
            
            return response
            
        except Exception as e:
            processing_time = time.time() - start_time
            logger.error(
                f"Request failed: {request.method} {request.url.path} "
                f"after {processing_time:.2f}s - {str(e)}"
            )
            raise

    def get_stats_summary(self) -> dict:
        """Get performance statistics summary"""
        summary = {}
        for endpoint, times in self.request_stats.items():
            if times:
                summary[endpoint] = {
                    "count": len(times),
                    "avg_time": sum(times) / len(times),
                    "max_time": max(times),
                    "min_time": min(times)
                }
        return summary


class ErrorTrackingMiddleware:
    """Track and categorize application errors"""
    
    def __init__(self):
        self.error_counts = defaultdict(int)
        self.error_details = defaultdict(list)

    def __call__(self, request: Request, call_next: Callable):
        return self.process_request(request, call_next)

    async def process_request(self, request: Request, call_next: Callable):
        try:
            response = await call_next(request)
            return response
            
        except HTTPException as e:
            # Track HTTP exceptions
            error_key = f"HTTP_{e.status_code}"
            self.error_counts[error_key] += 1
            
            error_info = {
                "timestamp": datetime.now().isoformat(),
                "endpoint": f"{request.method} {request.url.path}",
                "status_code": e.status_code,
                "detail": e.detail,
                "client_ip": request.client.host if request.client else "unknown"
            }
            
            self.error_details[error_key].append(error_info)
            
            # Keep only last 50 errors per type
            if len(self.error_details[error_key]) > 50:
                self.error_details[error_key] = self.error_details[error_key][-50:]
            
            logger.error(f"HTTP Exception: {e.status_code} - {e.detail}")
            raise
            
        except Exception as e:
            # Track general exceptions
            error_key = f"Exception_{type(e).__name__}"
            self.error_counts[error_key] += 1
            
            error_info = {
                "timestamp": datetime.now().isoformat(),
                "endpoint": f"{request.method} {request.url.path}",
                "error_type": type(e).__name__,
                "error_message": str(e),
                "client_ip": request.client.host if request.client else "unknown"
            }
            
            self.error_details[error_key].append(error_info)
            
            if len(self.error_details[error_key]) > 50:
                self.error_details[error_key] = self.error_details[error_key][-50:]
            
            logger.error(f"Unhandled exception: {type(e).__name__} - {str(e)}")
            raise

    def get_error_summary(self) -> dict:
        """Get error statistics summary"""
        return {
            "error_counts": dict(self.error_counts),
            "total_errors": sum(self.error_counts.values()),
            "error_types": list(self.error_counts.keys())
        }


class HealthCheckMiddleware:
    """Monitor application health and availability"""
    
    def __init__(self):
        self.start_time = time.time()
        self.request_count = 0
        self.error_count = 0
        self.last_health_check = time.time()

    def __call__(self, request: Request, call_next: Callable):
        return self.process_request(request, call_next)

    async def process_request(self, request: Request, call_next: Callable):
        self.request_count += 1
        
        try:
            response = await call_next(request)
            self.last_health_check = time.time()
            return response
            
        except Exception as e:
            self.error_count += 1
            raise

    def get_health_status(self) -> dict:
        """Get current health status"""
        uptime = time.time() - self.start_time
        error_rate = (self.error_count / max(self.request_count, 1)) * 100
        
        status = "healthy"
        if error_rate > 10:  # More than 10% error rate
            status = "unhealthy"
        elif error_rate > 5:  # More than 5% error rate
            status = "degraded"
        
        return {
            "status": status,
            "uptime_seconds": uptime,
            "total_requests": self.request_count,
            "total_errors": self.error_count,
            "error_rate_percent": error_rate,
            "last_request_time": self.last_health_check
        }


# Composite middleware class
class MediFastMiddleware:
    """Combine all middleware components"""
    
    def __init__(self):
        self.rate_limiter = RateLimitMiddleware(calls=200, period=3600)  # 200 requests per hour
        self.security_headers = SecurityHeadersMiddleware()
        self.request_validator = RequestValidationMiddleware()
        self.performance_monitor = PerformanceMonitoringMiddleware(slow_threshold=2.0)
        self.error_tracker = ErrorTrackingMiddleware()
        self.health_checker = HealthCheckMiddleware()

    def get_middleware_stack(self):
        """Get list of middleware in correct order"""
        return [
            self.health_checker,
            self.rate_limiter,
            self.security_headers,
            self.request_validator,
            self.performance_monitor,
            self.error_tracker
        ]

    def get_monitoring_data(self) -> dict:
        """Get combined monitoring data from all middleware"""
        return {
            "health": self.health_checker.get_health_status(),
            "performance": self.performance_monitor.get_stats_summary(),
            "errors": self.error_tracker.get_error_summary(),
            "timestamp": datetime.now().isoformat()
        }