variable "project_id"        { type = string }
variable "region"            { type = string }
variable "env"               { type = string }
variable "network_self_link" { type = string }
variable "db_name"           { type = string; default = "zoiko" }
variable "db_tier"           { type = string; default = "db-g1-small" }
