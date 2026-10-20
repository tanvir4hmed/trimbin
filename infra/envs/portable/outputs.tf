output "host_name" {
  value = google_compute_instance.host.name
}
output "private_ip" {
  value = google_compute_instance.host.network_interface[0].network_ip
}
output "data_disk" {
  value = google_compute_disk.data.name
}
