variable "project_id" {
  type = string
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "Supply a GCP project ID."
  }
}
variable "region" {
  type    = string
  default = "us-central1"
}
variable "zone" {
  type    = string
  default = "us-central1-a"
}
variable "name" {
  type    = string
  default = "trimbin-portable"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.name))
    error_message = "Use a valid 6-30 character service account/host name."
  }
}
variable "machine_type" {
  type    = string
  default = "e2-standard-4"
}
variable "data_disk_gb" {
  type    = number
  default = 100
  validation {
    condition     = var.data_disk_gb >= 30
    error_message = "At least 30 GiB is required for this foundation, not a footage sizing claim."
  }
}
variable "boot_image" {
  type        = string
  description = "Explicit approved Ubuntu 24.04 image ID; no moving family default."
}
variable "release_bucket" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9._-]+[a-z0-9]$", var.release_bucket))
    error_message = "Supply a bucket name, not a URL."
  }
}
variable "release_object" {
  type        = string
  description = "Immutable tar.gz package object, containing deploy/foundation and tools."
  validation {
    condition     = can(regex("^[A-Za-z0-9/_.-]+$", var.release_object))
    error_message = "Release object may contain letters, digits, slash, underscore, dot and dash."
  }
}
variable "release_sha256" {
  type = string
  validation {
    condition     = can(regex("^[0-9a-f]{64}$", var.release_sha256))
    error_message = "Supply the immutable package SHA256."
  }
}
variable "foundation_secret_id" {
  type        = string
  description = "Existing Secret Manager secret name containing foundation secret JSON, never its value."
  validation {
    condition     = can(regex("^[A-Za-z0-9_-]+$", var.foundation_secret_id))
    error_message = "Supply only the Secret Manager secret name."
  }
}
