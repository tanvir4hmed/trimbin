/**
 * The address, the certificate, and the cache.
 *
 * A load balancer rather than Cloud Run's own domain mapping, because the
 * proxies have to sit behind a CDN. Video egress is the largest infrastructure
 * cost in this system by a wide margin, and a demo where everyone watches the
 * same footage is the best possible case for caching: one visitor pays for the
 * origin fetch and everyone after them is served from the edge.
 */

resource "google_compute_managed_ssl_certificate" "main" {
  name = "${local.name}-cert"

  managed {
    domains = [var.domain]
  }

  # Google will not issue until the A record resolves here, so replacement is a
  # slow operation and the certificate must be created before the thing that
  # depends on it is destroyed.
  lifecycle {
    create_before_destroy = true
  }
}

# ---------------------------------------------------------------------------
# Backends.
# ---------------------------------------------------------------------------

resource "google_compute_region_network_endpoint_group" "api" {
  name                  = "${local.name}-api-neg"
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = google_cloud_run_v2_service.api.name
  }
}

resource "google_compute_backend_service" "api" {
  name                  = "${local.name}-api-backend"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"

  backend {
    group = google_compute_region_network_endpoint_group.api.id
  }

  # Not cached. Responses depend on who is asking, and the public routes set
  # their own Cache-Control which the browser honours.
  enable_cdn = false

  log_config {
    enable      = true
    sample_rate = 0.1 # enough to spot a pattern, not enough to pay for every hit
  }
}

# The bucket holding proxies and sprites, served through the CDN. This is the
# path that would otherwise dominate the bill.
resource "google_compute_backend_bucket" "media" {
  name        = "${local.name}-media-backend"
  bucket_name = google_storage_bucket.proxies.name
  enable_cdn  = true

  cdn_policy {
    cache_mode = "CACHE_ALL_STATIC"

    # A segment is immutable once written — its name contains its position and
    # its content never changes — so it can be held for a long time. Overrides
    # change which segments a playlist references, never the segments
    # themselves.
    default_ttl = 2592000 # 30 days
    max_ttl     = 2592000
    client_ttl  = 86400

    # Serve stale rather than stampeding the origin when a popular segment
    # expires during a burst.
    serve_while_stale = 86400

    # Collapse concurrent misses for the same object into one origin fetch.
    # Without this, a demo shared with a room full of people fetches the same
    # first segment once per viewer.
    request_coalescing = true

    # No cache key policy: segment names are already unique and immutable, so
    # the default key is exactly right. Narrowing it further would only create
    # a way for two different objects to collide.
  }
}

# Public read on the proxy bucket. These are low-resolution derivatives of demo
# footage, and the CDN needs to fetch them without credentials. Originals stay
# private and are never served this way.
resource "google_storage_bucket_iam_member" "proxies_public" {
  bucket = google_storage_bucket.proxies.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# ---------------------------------------------------------------------------
# Routing.
# ---------------------------------------------------------------------------

resource "google_compute_url_map" "main" {
  name            = "${local.name}-urlmap"
  default_service = google_compute_backend_service.api.id

  host_rule {
    hosts        = [var.domain]
    path_matcher = "main"
  }

  path_matcher {
    name            = "main"
    default_service = google_compute_backend_service.api.id

    path_rule {
      paths   = ["/media/*"]
      service = google_compute_backend_bucket.media.id

      route_action {
        url_rewrite {
          path_prefix_rewrite = "/"
        }
      }
    }
  }
}

resource "google_compute_target_https_proxy" "main" {
  name             = "${local.name}-https-proxy"
  url_map          = google_compute_url_map.main.id
  ssl_certificates = [google_compute_managed_ssl_certificate.main.id]
}

resource "google_compute_global_forwarding_rule" "https" {
  name                  = "${local.name}-https"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.ingress.address
  port_range            = "443"
  target                = google_compute_target_https_proxy.main.id
}

# Redirect plain HTTP rather than refusing it. Someone typing the domain without
# a scheme should arrive, not see a connection error.
resource "google_compute_url_map" "redirect" {
  name = "${local.name}-redirect"

  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

resource "google_compute_target_http_proxy" "redirect" {
  name    = "${local.name}-http-proxy"
  url_map = google_compute_url_map.redirect.id
}

resource "google_compute_global_forwarding_rule" "http" {
  name                  = "${local.name}-http"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.ingress.address
  port_range            = "80"
  target                = google_compute_target_http_proxy.redirect.id
}
