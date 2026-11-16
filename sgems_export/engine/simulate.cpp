// Seeded, single-structure SGSIM and categorical median-indicator SISIM.
#include "spatial.h"
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <random>
#include <GsTL/kriging/kriging_weights.h>
#include <GsTL/kriging/SK_constraints.h>
#include <GsTL/simulation/sequential_simulation.h>

struct Node : Sample {
    int index;
    bool is_informed() const { return std::isfinite(value); }
};
struct Search : Neighbours {
    std::multimap<double, Sample> known;
    double range;
    bool is_valid() const { return true; }
    void insert_sample(const Sample& s) { known.emplace(s.position.x,s); }
    void find_neighbors(const Node& node) {
        clear();
        std::vector<std::pair<double,Sample>> candidates;
        const Point target=node.location();
        const auto end=known.upper_bound(target.x+range);
        for(auto it=known.lower_bound(target.x-range); it!=end; ++it) {
            double d=distance(it->second.location(),target);
            if(d<range) candidates.emplace_back(d,it->second);
        }
        auto limit=candidates.begin()+std::min<size_t>(16,candidates.size());
        std::partial_sort(candidates.begin(),limit,candidates.end(),[](const auto& a,const auto& b){
            return a.first<b.first;
        });
        for(auto it=candidates.begin();it!=limit;++it) push_back(it->second);
    }
};
struct Distribution {
    double mean=0, variance=1;
    std::vector<double> probabilities;
};
struct Estimator {
    Spherical covariance;
    Distribution marginal;
    int operator()(const Node& node, Search& neighbors, Distribution& result) {
        SK_constraints constraints;
        std::vector<double> weights;
        result=marginal;
        if(kriging_weights(weights,result.variance,node.location(),neighbors,covariance,constraints)) return 1;
        if(!std::isfinite(result.variance) || result.variance < -1e-6) return 1;
        for(size_t i=0;i<neighbors.size();++i) {
            if(result.probabilities.empty()) result.mean+=weights[i]*neighbors[i].value;
            else {
                for(size_t k=0;k<result.probabilities.size();++k)
                    result.probabilities[k]+=weights[i]*((neighbors[i].value==k)-marginal.probabilities[k]);
            }
        }
        for(double& p:result.probabilities) p=std::max(0.,std::min(1.,p));
        return 0;
    }
};
struct Draw {
    std::mt19937& rng;
    Search& search;
    void operator()(Node& n,const Distribution& d) {
        if(d.probabilities.empty())
            n.value=d.mean+std::sqrt(std::max(0.,d.variance))*std::normal_distribution<double>()(rng);
        else n.value=std::discrete_distribution<int>(d.probabilities.begin(),d.probabilities.end())(rng);
        search.insert_sample(n);
    }
};
int main(int argc,char** argv) {
    if(argc!=4) return 1;
    bool categorical=std::string(argv[1])=="sisim";
    std::mt19937 rng(std::stoul(argv[2]));
    int nr=std::stoi(argv[3]), n, m;
    Spherical cov;
    if(!(std::cin>>cov.range>>n>>m) || n<2 || m<1 || nr<1 || cov.range<=0) return 1;
    Search initial;
    initial.range=cov.range;
    Distribution marginal;
    std::map<std::tuple<double,double,double>,double> hard;
    for(int i=0;i<n;++i) {
        Sample s;
        if(!(std::cin>>s.position.x>>s.position.y>>s.position.z>>s.value)) return 1;
        initial.insert_sample(s);
        hard[{s.position.x,s.position.y,s.position.z}]=s.value;
        if(categorical) {
            if(s.value<0 || s.value>=n || s.value!=std::floor(s.value)) return 1;
            size_t k=static_cast<size_t>(s.value);
            if(marginal.probabilities.size()<=k) marginal.probabilities.resize(k+1,0);
            marginal.probabilities[k]+=1./n;
        }
    }
    std::vector<Node> grid(m);
    for(int i=0;i<m;++i) {
        Node& node=grid[i];
        auto& p=node.position;
        if(!(std::cin>>p.x>>p.y>>p.z)) return 1;
        node.index=i;
        auto found=hard.find({p.x,p.y,p.z});
        node.value=found==hard.end()?std::numeric_limits<double>::quiet_NaN():found->second;
    }
    std::cout<<std::setprecision(17);
    for(int r=0;r<nr;++r) {
        Search search=initial;
        auto path=grid;
        std::shuffle(path.begin(),path.end(),rng);
        Distribution conditional;
        Estimator estimator{cov,marginal};
        Draw draw{rng,search};
        if(sequential_simulation(path.begin(),path.end(),search,conditional,estimator,marginal,draw)) return 2;
        std::vector<double> realization(m);
        for(const auto& node:path) realization[node.index]=node.value;
        for(double value:realization) std::cout<<value<<'\n';
    }
}
