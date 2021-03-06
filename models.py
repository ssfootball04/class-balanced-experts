import torch.nn as nn
import torch.nn.functional as F
from utils import *

class CalibrateExperts(nn.Module):
    
    def __init__(self, dataset, manyshotClassMask, mediumshotClassMask, fewshotClassMask, *args):
        super(CalibrateExperts, self).__init__()
        self.dataset = dataset

        # ranges of manyshot, mediumshot and fewshot logits
        if(dataset=='imagenet'):
            self.manyshotRange = (0, 392)
            self.mediumshotRange = (392, 866)
            self.fewshotRange = (866, 1003)
        else:
            self.manyshotRange = (0, 133)
            self.mediumshotRange = (133, 296)
            self.fewshotRange = (296, 368)

        # learning temp per index
        self.manyshotTemp = nn.Parameter(torch.ones(1, self.manyshotRange[1] - self.manyshotRange[0])  )
        self.mediumshotTemp = nn.Parameter(torch.ones(1, self.mediumshotRange[1] - self.mediumshotRange[0]) )
        self.fewshotTemp = nn.Parameter(torch.ones(1, self.fewshotRange[1] - self.fewshotRange[0]) )
        
        # learning bias per index
        self.manyshotBias = nn.Parameter(torch.ones(1, self.manyshotRange[1] - self.manyshotRange[0]))
        self.mediumshotBias = nn.Parameter(torch.ones(1, self.mediumshotRange[1] - self.mediumshotRange[0]))
        self.fewshotBias = nn.Parameter(torch.ones(1, self.fewshotRange[1] - self.fewshotRange[0]))

        self.manyshotClassMask, self.mediumshotClassMask, self.fewshotClassMask = manyshotClassMask, mediumshotClassMask, fewshotClassMask
    
    def forward(self, x, *args):
        
        # slicing logits
        manyshotLogits = x[:,self.manyshotRange[0]:self.manyshotRange[1]]
        mediumshotLogits = x[:,self.mediumshotRange[0]:self.mediumshotRange[1]]
        fewshotLogits = x[:,self.fewshotRange[0]:self.fewshotRange[1]]
        
        # per index temperature scaling, bias, and softmax    
        manyshotProbs = F.softmax((self.manyshotTemp * manyshotLogits) + self.manyshotBias, dim=1)[:,:-1]
        mediumshotProbs = F.softmax((self.mediumshotTemp * mediumshotLogits) + self.mediumshotBias, dim=1)[:,:-1]
        fewshotProbs = F.softmax((self.fewshotTemp * fewshotLogits) + self.fewshotBias, dim=1)[:,:-1]
        
        # concatenating, normalising, and taking log (loss function is NLL)    
        y = Variable(torch.zeros(x.shape[0], x.shape[1]-3), requires_grad=True).cuda()     # removing reject option indices
        y[:,self.manyshotClassMask] = manyshotProbs
        y[:,self.mediumshotClassMask] = mediumshotProbs
        y[:,self.fewshotClassMask] = fewshotProbs
        y = y / y.sum(dim=1).unsqueeze(1)
        y = torch.log(y)

        return y

class DotProduct_Classifier(nn.Module):

    def __init__(self, num_classes=1000, feat_dim=512, use_logits=False, *args):
        super(DotProduct_Classifier, self).__init__()
        self.num_classes = num_classes
        self.feat_dim = feat_dim
        self.fc = nn.Linear(feat_dim, num_classes)
        self.use_logits = use_logits

    def forward(self, x, *args):
        x = self.fc(x)
        if( not self.use_logits ):        
            x = F.log_softmax(x, dim=1)                                  
        return x

##############################################
######### based on Liu et. al's code #########
##############################################

def conv3x3(in_planes, out_planes, stride=1):
    """3x3 convolution with padding"""
    return nn.Conv2d(in_planes, out_planes, kernel_size=3, stride=stride,
                     padding=1, bias=False)

class BasicBlock(nn.Module):
    expansion = 1

    def __init__(self, inplanes, planes, stride=1, downsample=None):
        super(BasicBlock, self).__init__()
        self.conv1 = conv3x3(inplanes, planes, stride)
        self.bn1 = nn.BatchNorm2d(planes)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = conv3x3(planes, planes)
        self.bn2 = nn.BatchNorm2d(planes)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x):
        residual = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)

        if self.downsample is not None:
            residual = self.downsample(x)

        out += residual
        out = self.relu(out)

        return out
    
class Bottleneck(nn.Module):
    expansion = 4

    def __init__(self, inplanes, planes, stride=1, downsample=None):
        super(Bottleneck, self).__init__()
        self.conv1 = nn.Conv2d(inplanes, planes, kernel_size=1, bias=False)
        self.bn1 = nn.BatchNorm2d(planes)
        self.conv2 = nn.Conv2d(planes, planes, kernel_size=3, stride=stride,
                               padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(planes)
        self.conv3 = nn.Conv2d(planes, planes * 4, kernel_size=1, bias=False)
        self.bn3 = nn.BatchNorm2d(planes * 4)
        self.relu = nn.ReLU(inplace=True)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x):
        residual = x

        out = self.conv1(x)
        out = self.bn1(out)
        out = self.relu(out)

        out = self.conv2(out)
        out = self.bn2(out)
        out = self.relu(out)

        out = self.conv3(out)
        out = self.bn3(out)

        if self.downsample is not None:
            residual = self.downsample(x)

        out += residual
        out = self.relu(out)

        return out

class ResNet(nn.Module):

    def __init__(self, block, layers, use_fc=False, dropout=None):
        self.inplanes = 64
        super(ResNet, self).__init__()
        self.conv1 = nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3,
                               bias=False)
        self.bn1 = nn.BatchNorm2d(64)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)
        self.layer1 = self._make_layer(block, 64, layers[0])
        self.layer2 = self._make_layer(block, 128, layers[1], stride=2)
        self.layer3 = self._make_layer(block, 256, layers[2], stride=2)
        self.layer4 = self._make_layer(block, 512, layers[3], stride=2)
        self.avgpool = nn.AvgPool2d(7, stride=1)
        
        self.use_fc = use_fc
        self.use_dropout = True if dropout else False

        if self.use_fc:
            self.fc_add = nn.Linear(512*block.expansion, 512)

        if self.use_dropout:
            print('Using dropout.')
            self.dropout = nn.Dropout(p=dropout)
  
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                n = m.kernel_size[0] * m.kernel_size[1] * m.out_channels
                m.weight.data.normal_(0, math.sqrt(2. / n))
            elif isinstance(m, nn.BatchNorm2d):
                m.weight.data.fill_(1)
                m.bias.data.zero_()

    def _make_layer(self, block, planes, blocks, stride=1):
        downsample = None
        if stride != 1 or self.inplanes != planes * block.expansion:
            downsample = nn.Sequential(
                nn.Conv2d(self.inplanes, planes * block.expansion,
                          kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm2d(planes * block.expansion),
            )

        layers = []
        layers.append(block(self.inplanes, planes, stride, downsample))
        self.inplanes = planes * block.expansion
        for i in range(1, blocks):
            layers.append(block(self.inplanes, planes))

        return nn.Sequential(*layers)

    def forward(self, x, *args):
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)

        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)
    
        feature_maps = None

        x = self.avgpool(x)
        
        x = x.view(x.size(0), -1)
        
        if self.use_fc:
            x = F.relu(self.fc_add(x))

        if self.use_dropout:
            x = self.dropout(x)

        return x, feature_maps

def create_model_resnet10(use_fc=True, dropout=None, dataset=None, test=False, *args):
    
    resnet10 = ResNet(BasicBlock, [1, 1, 1, 1], use_fc=use_fc, dropout=None)
    return resnet10

def create_model_resnet152(use_fc=True, dropout=None, dataset=None, caffe=False, test=False):
    
    resnet152 = ResNet(Bottleneck, [3, 8, 36, 3], use_fc=use_fc, dropout=None)    
    if caffe:
        print('Loading Caffe Pretrained ResNet 152 Weights.')
        resnet152 = init_weights(model=resnet152,
                                 weights_path='./data/caffe_resnet152.pth',
                                 caffe=True)
    return resnet152

