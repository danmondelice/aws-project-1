resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true


  tags = {
    Name = "${local.name_prefix}-vpc"
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_subnet" "public_az1" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.20.0.0/27"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true


  tags = {
    Name = "${local.name_prefix}-public-az1"
    Tier = "public"
  }
}


resource "aws_subnet" "public_az2" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.20.0.32/27"
  availability_zone       = data.aws_availability_zones.available.names[1]
  map_public_ip_on_launch = true


  tags = {
    Name = "${local.name_prefix}-public-az2"
    Tier = "public"
  }
}


resource "aws_subnet" "app_az1" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.20.1.0/24"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = false


  tags = {
    Name = "${local.name_prefix}-app-az1"
    Tier = "application"
  }
}


resource "aws_subnet" "app_az2" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.20.2.0/24"
  availability_zone       = data.aws_availability_zones.available.names[1]
  map_public_ip_on_launch = false


  tags = {
    Name = "${local.name_prefix}-app-az2"
    Tier = "application"
  }
}


resource "aws_subnet" "db_az1" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.20.3.0/27"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = false


  tags = {
    Name = "${local.name_prefix}-db-az1"
    Tier = "database"
  }
}


resource "aws_subnet" "db_az2" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.20.3.32/27"
  availability_zone       = data.aws_availability_zones.available.names[1]
  map_public_ip_on_launch = false


  tags = {
    Name = "${local.name_prefix}-db-az2"
    Tier = "database"
  }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id


  tags = {
    Name = "${local.name_prefix}-igw"
  }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id


  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }


  tags = {
    Name = "${local.name_prefix}-public-rt"
  }
}

resource "aws_route_table_association" "public_az1" {
  subnet_id      = aws_subnet.public_az1.id
  route_table_id = aws_route_table.public.id
}


resource "aws_route_table_association" "public_az2" {
  subnet_id      = aws_subnet.public_az2.id
  route_table_id = aws_route_table.public.id
}

resource "aws_eip" "nat" {
  count  = var.ha_mode ? 2 : 1
  domain = "vpc"


  tags = {
    Name = "${local.name_prefix}-nat-eip-${count.index + 1}"
  }
}


resource "aws_nat_gateway" "nat" {
  count = var.ha_mode ? 2 : 1


  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = count.index == 0 ? aws_subnet.public_az1.id : aws_subnet.public_az2.id


  depends_on = [
    aws_internet_gateway.main,
    aws_route_table_association.public_az1,
    aws_route_table_association.public_az2
  ]


  tags = {
    Name = "${local.name_prefix}-nat-${count.index + 1}"
  }
}

resource "aws_route_table" "app_az1" {
  vpc_id = aws_vpc.main.id


  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.nat[0].id
  }


  tags = {
    Name = "${local.name_prefix}-app-az1-rt"
  }
}


resource "aws_route_table" "app_az2" {
  vpc_id = aws_vpc.main.id


  route {
    cidr_block = "0.0.0.0/0"


    nat_gateway_id = var.ha_mode ? aws_nat_gateway.nat[1].id : aws_nat_gateway.nat[0].id
  }


  tags = {
    Name = "${local.name_prefix}-app-az2-rt"
  }
}

resource "aws_route_table_association" "app_az1" {
  subnet_id      = aws_subnet.app_az1.id
  route_table_id = aws_route_table.app_az1.id
}


resource "aws_route_table_association" "app_az2" {
  subnet_id      = aws_subnet.app_az2.id
  route_table_id = aws_route_table.app_az2.id
}

resource "aws_route_table" "database" {
  vpc_id = aws_vpc.main.id


  tags = {
    Name = "${local.name_prefix}-database-rt"
  }
}


resource "aws_route_table_association" "db_az1" {
  subnet_id      = aws_subnet.db_az1.id
  route_table_id = aws_route_table.database.id
}


resource "aws_route_table_association" "db_az2" {
  subnet_id      = aws_subnet.db_az2.id
  route_table_id = aws_route_table.database.id
}
