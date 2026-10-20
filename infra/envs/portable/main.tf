terraform {
  required_version = ">= 1.9"
  backend "gcs" {}
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

# This environment is deliberately separate from the live legacy state.
# No workflow applies it until host/budget and migration are approved.
resource "google_compute_network" "studio" {
  name                    = "${var.name}-network"
  auto_create_subnetworks = false
}
resource "google_compute_subnetwork" "studio" {
  name          = "${var.name}-subnet"
  ip_cidr_range = "10.72.0.0/24"
  network       = google_compute_network.studio.id
}
resource "google_compute_firewall" "iap" {
  name          = "${var.name}-iap"
  network       = google_compute_network.studio.id
  source_ranges = ["35.235.240.0/20"]
  target_tags   = [var.name]
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}
resource "google_service_account" "host" {
  account_id   = var.name
  display_name = "Portable editorial foundation"
}
resource "google_storage_bucket_iam_member" "package" {
  bucket = var.release_bucket
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.host.email}"
}
resource "google_secret_manager_secret_iam_member" "foundation" {
  secret_id = var.foundation_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.host.email}"
}
resource "google_compute_disk" "data" {
  name = "${var.name}-data"
  type = "pd-ssd"
  size = var.data_disk_gb
  lifecycle {
    prevent_destroy = true
  }
}
resource "google_compute_instance" "host" {
  name                = var.name
  machine_type        = var.machine_type
  deletion_protection = true
  tags                = [var.name]
  boot_disk {
    initialize_params {
      image = var.boot_image
      size  = 30
    }
  }
  attached_disk {
    source      = google_compute_disk.data.id
    device_name = "editorial-data"
  }
  network_interface {
    subnetwork = google_compute_subnetwork.studio.id
    # Outbound package/model access; firewall exposes no database ports.
    access_config {}
  }
  service_account {
    email  = google_service_account.host.email
    scopes = ["cloud-platform"]
  }
  metadata = {
    enable-oslogin         = "TRUE"
    block-project-ssh-keys = "TRUE"
  }
  metadata_startup_script = templatefile("${path.module}/startup.sh.tftpl", {
    release_bucket       = var.release_bucket
    release_object       = var.release_object
    release_sha256       = var.release_sha256
    foundation_secret_id = var.foundation_secret_id
    project_id           = var.project_id
  })
  depends_on = [
    google_storage_bucket_iam_member.package,
    google_secret_manager_secret_iam_member.foundation
  ]
}
