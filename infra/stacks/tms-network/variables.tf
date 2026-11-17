variable "nat_gateway_count" {
  description = "NAT 게이트웨이 개수. 0(기본, 꺼 둠), 1(개발: 두 AZ가 AZ-a NAT 공유), 2(시연: AZ마다 1개)"
  type        = number
  default     = 0

  validation {
    condition     = contains([0, 1, 2], var.nat_gateway_count)
    error_message = "nat_gateway_count는 0, 1, 2 중 하나여야 한다."
  }
}

variable "bastion_ssh_cidrs" {
  description = "배스천 SSH(22)를 허용할 주소. 기본은 전체 허용 + 키 인증만(2026-11-16 결정)"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
