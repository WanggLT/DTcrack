import os.path
import warnings

import torch
from torch import nn
# from models.mynet import *
from models.mynet1 import *
# from models.mynet_sra import *
import torch.nn.functional as F
from models.attention import eca_block, CA_Block


class BasicConv2d(nn.Module):
    def __init__(self, in_planes, out_planes, kernel_size, stride=1, padding=0, dilation=1):
        super(BasicConv2d, self).__init__()

        self.conv = nn.Conv2d(in_planes, out_planes,
                              kernel_size=kernel_size, stride=stride,
                              padding=padding, dilation=dilation, bias=False)
        self.bn = nn.BatchNorm2d(out_planes)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        x = self.conv(x)
        x = self.bn(x)
        return x


class Encoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = transxnet_t(pretrained=False)

    def forward(self, x):
        f1, f2, f3, f4 = self.backbone(x)
        return f1, f2, f3, f4


class SDI(nn.Module):
    def __init__(self, channel):
        super().__init__()

        self.convs = nn.ModuleList(
            [nn.Conv2d(channel, channel, kernel_size=3, stride=1, padding=1)] * 4)

    def forward(self, xs, anchor):
        ans = torch.ones_like(anchor)
        target_size = anchor.shape[-1]

        for i, x in enumerate(xs):
            if x.shape[-1] > target_size:
                x = F.adaptive_avg_pool2d(x, (target_size, target_size))
            elif x.shape[-1] < target_size:
                x = F.interpolate(x, size=(target_size,target_size), mode='bilinear', align_corners=True)

            ans = ans * self.convs[i](x)

        return ans


class CrackTransUnet(nn.Module):
    def __init__(self, channel=32, n_classes=2, deep_supervision=True):
        super().__init__()
        self.deep_supervision = deep_supervision

        self.encoder = Encoder()
        self.eca_1 = eca_block(64)
        self.ca_1 = CA_Block(64)
        # self.eca_1 = eca_block(48)
        # self.ca_1 = CA_Block(48)

        self.eca_2 = eca_block(128)
        self.ca_2 = CA_Block(128)
        # self.eca_2 = eca_block(96)
        # self.ca_2 = CA_Block(96)

        self.eca_3 = eca_block(320)
        self.ca_3 = CA_Block(320)
        # self.eca_3 = eca_block(224)
        # self.ca_3 = CA_Block(224)

        self.eca_4 = eca_block(512)
        self.ca_4 = CA_Block(512)
        # self.eca_4 = eca_block(448)
        # self.ca_4 = CA_Block(448)

        self.Translayer_1 = BasicConv2d(64, channel, 1)
        self.Translayer_2 = BasicConv2d(128, channel, 1)
        self.Translayer_3 = BasicConv2d(320, channel, 1)
        self.Translayer_4 = BasicConv2d(512, channel, 1)
        # self.Translayer_1 = BasicConv2d(48, channel, 1)
        # self.Translayer_2 = BasicConv2d(96, channel, 1)
        # self.Translayer_3 = BasicConv2d(224, channel, 1)
        # self.Translayer_4 = BasicConv2d(448, channel, 1)

        self.sdi_1 = SDI(channel)
        self.sdi_2 = SDI(channel)
        self.sdi_3 = SDI(channel)
        self.sdi_4 = SDI(channel)

        self.seg_outs = nn.ModuleList([nn.Conv2d(channel, n_classes, 1, 1)] * 4)

        self.deconv2 = nn.ConvTranspose2d(channel, channel, kernel_size=4, stride=2, padding=1, bias=False)
        self.deconv3 = nn.ConvTranspose2d(channel, channel, kernel_size=4, stride=2, padding=1, bias=False)
        self.deconv4 = nn.ConvTranspose2d(channel, channel, kernel_size=4, stride=2, padding=1, bias=False)
        self.deconv5 = nn.ConvTranspose2d(channel, channel, kernel_size=4, stride=2, padding=1, bias=False)

    def forward(self, x):
        seg_outs = []
        f1, f2, f3, f4 = self.encoder(x)

        f1 = self.eca_1(f1) * f1
        f1 = self.ca_1(f1) * f1
        f1 = self.Translayer_1(f1)

        f2 = self.eca_2(f2) * f2
        f2 = self.ca_2(f2) * f2
        f2 = self.Translayer_2(f2)

        f3 = self.eca_3(f3) * f3
        f3 = self.ca_3(f3) * f3
        f3 = self.Translayer_3(f3)

        f4 = self.eca_4(f4) * f4
        f4 = self.ca_4(f4) * f4
        f4 = self.Translayer_4(f4)

        # f41 = self.sdi_4([f1, f2, f3, f4], f4)
        # f31 = self.sdi_3([f1, f2, f3, f4], f3)
        # f21 = self.sdi_2([f1, f2, f3, f4], f2)
        # f11 = self.sdi_1([f1, f2, f3, f4], f1)

        seg_outs.append(self.seg_outs[0](f4))

        y = self.deconv2(f4) + f3
        seg_outs.append(self.seg_outs[1](y))

        y = self.deconv3(y) + f2
        seg_outs.append(self.seg_outs[2](y))

        y = self.deconv4(y) + f1
        seg_outs.append(self.seg_outs[3](y))

        for i, o in enumerate(seg_outs):
            seg_outs[i] = F.interpolate(o, scale_factor=4, mode='bilinear')
        if self.deep_supervision:
            return seg_outs[::-1]
        else:
            return seg_outs[-1]


if __name__ == "__main__":
    image_tensor = torch.rand(2, 3, 256, 256)
    net = CrackTransUnet(n_classes=2, deep_supervision=True)
    device = torch.device('cuda:0')
    net = net.to(device)
    net = net.cuda()
    image_tensor = image_tensor.cuda()
    ys = net(image_tensor)
    for y in ys:
        print(y.shape)